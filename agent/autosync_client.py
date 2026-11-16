from __future__ import annotations

from typing import Any

import httpx


class AutoSyncError(RuntimeError):
    pass


class SyncPaused(AutoSyncError):
    """A direction was turned off on the console. Not a crash."""

    def __init__(self, direction: str, detail: str):
        self.direction = direction
        super().__init__(detail)


class AutoSyncClient:
    def __init__(self, base_url: str, token: str | None = None, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.token:
            headers["X-Tally-Installation-Token"] = self.token
        return headers

    def request(self, method: str, path: str, **kwargs) -> Any:
        url = f"{self.base_url}{path}"
        timeout = kwargs.pop("timeout", self.timeout)
        try:
            response = httpx.request(
                method,
                url,
                headers=self._headers(),
                timeout=timeout,
                **kwargs,
            )
        except httpx.TimeoutException as exc:
            raise AutoSyncError(f"Timed out calling {url}") from exc
        except httpx.HTTPError as exc:
            raise AutoSyncError(f"Unreachable {url}: {exc}") from exc
        if response.status_code >= 400:
            detail = response.text
            try:
                detail = response.json().get("detail", detail)
            except Exception:
                pass
            raise AutoSyncError(f"{response.status_code}: {detail}")
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    def pair(self, code: str, company: dict, interval_hours: int, brand_id: int | None = None) -> dict:
        return self.request(
            "POST",
            "/api/integrations/tally/pair",
            timeout=20.0,
            json={
                "code": code,
                "company_guid": company.get("guid") or "",
                "company_name": company.get("name") or "",
                "company_gstin": company.get("gstin") or "",
                "interval_hours": interval_hours,
                "brand_id": brand_id,
            },
        )

    def create_device_session(self, company: dict, agent_version: str | None = None) -> dict:
        return self.request(
            "POST",
            "/api/integrations/tally/device-sessions",
            timeout=20.0,
            json={
                "company_guid": company.get("guid") or "",
                "company_name": company.get("name") or "",
                "company_gstin": company.get("gstin") or "",
                "agent_version": agent_version,
            },
        )

    def poll_device_token(self, device_code: str) -> dict | None:
        """Return installation payload when approved, None while authorization is pending."""
        url = f"{self.base_url}/api/integrations/tally/device-sessions/token"
        try:
            response = httpx.request(
                "POST",
                url,
                headers=self._headers(),
                timeout=20.0,
                json={"device_code": device_code},
            )
        except httpx.TimeoutException as exc:
            raise AutoSyncError(f"Timed out calling {url}") from exc
        except httpx.HTTPError as exc:
            raise AutoSyncError(f"Unreachable {url}: {exc}") from exc
        if response.status_code == 400:
            try:
                detail = response.json().get("detail")
            except Exception:
                detail = None
            if isinstance(detail, dict) and detail.get("error") == "authorization_pending":
                return None
            if detail == "authorization_pending":
                return None
        if response.status_code >= 400:
            detail = response.text
            try:
                detail = response.json().get("detail", detail)
            except Exception:
                pass
            raise AutoSyncError(f"{response.status_code}: {detail}")
        return response.json()

    def import_batch(self, payload: dict) -> dict:
        return self._direction_request("inbound", "POST", "/api/integrations/tally/import", json=payload)

    def outbound_feed(self, *, limit: int = 50) -> dict:
        return self.request("GET", f"/api/integrations/tally/outbound?limit={int(limit)}")

    def acknowledge(self, items: list[dict]) -> dict:
        return self._direction_request(
            "outbound",
            "POST",
            "/api/integrations/tally/acknowledge",
            json={"items": items},
        )

    def _direction_request(self, direction: str, method: str, path: str, **kwargs) -> Any:
        try:
            return self.request(method, path, **kwargs)
        except AutoSyncError as exc:
            text = str(exc)
            if text.startswith("409:") and "disabled" in text.lower():
                raise SyncPaused(direction, text) from exc
            raise

    def heartbeat(self, state: str, import_failed: bool = False) -> None:
        self.request("POST", "/api/integrations/tally/heartbeat", json={"state": state, "import_failed": import_failed}, timeout=3)

    def status(self) -> dict:
        return self.request("GET", "/api/integrations/tally/status")

    def update_mapping(self, mapping: dict) -> dict:
        return self.request("PUT", "/api/integrations/tally/mapping", json={"mapping": mapping})
