from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from agent.autosync_client import AutoSyncClient
from agent.security import load_token, save_token
from agent.storage import LocalStore


PRESETS = (
    {
        "id": "pluschwood",
        "label": "Pluschwood Console",
        "base_url": "https://console.pluschwood.com",
    },
    {
        "id": "autosync",
        "label": "AutoSync",
        "base_url": "https://autosync.app",
    },
)


@dataclass
class Destination:
    id: str
    label: str
    base_url: str
    company_guid: str = ""
    company_name: str = ""

    def token_path(self, data_dir: Path) -> Path:
        return data_dir / f"destination-{self.id}.token"

    def client(self, data_dir: Path, token: str | None = None) -> AutoSyncClient:
        return AutoSyncClient(self.base_url, token if token is not None else load_token(self.token_path(data_dir)))


def normalize_base_url(url: str) -> str:
    text = (url or "").strip().rstrip("/")
    if not text:
        raise ValueError("Base URL is required")
    if "://" not in text:
        text = "https://" + text
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"Invalid base URL: {url}")
    return f"{parsed.scheme}://{parsed.netloc}"


def slug_from_url(url: str) -> str:
    host = urlparse(normalize_base_url(url)).netloc.lower()
    host = host.removeprefix("www.")
    slug = re.sub(r"[^a-z0-9]+", "-", host).strip("-")
    return slug or uuid.uuid4().hex[:8]


def list_destinations(store: LocalStore) -> list[Destination]:
    rows = store.get_meta("destinations") or []
    return [Destination(id=row["id"], label=row.get("label") or row["id"], base_url=row["base_url"], company_guid=row.get("company_guid", ""), company_name=row.get("company_name", "")) for row in rows]


def save_destinations(store: LocalStore, destinations: list[Destination]) -> None:
    store.set_meta(
        "destinations",
        [{"id": item.id, "label": item.label, "base_url": item.base_url, "company_guid": item.company_guid, "company_name": item.company_name} for item in destinations],
    )


def get_destination(store: LocalStore, destination_id: str) -> Destination | None:
    for item in list_destinations(store):
        if item.id == destination_id:
            return item
    return None


def upsert_destination(
    store: LocalStore,
    *,
    label: str,
    base_url: str,
    destination_id: str | None = None,
    company_guid: str = "",
    company_name: str = "",
) -> Destination:
    url = normalize_base_url(base_url)
    destinations = list_destinations(store)
    for existing in destinations:
        if destination_id and existing.id == destination_id:
            existing.label = label or existing.label
            existing.base_url = url
            existing.company_guid = company_guid
            existing.company_name = company_name or existing.company_name
            save_destinations(store, destinations)
            return existing
        if existing.base_url.lower() == url.lower() and existing.company_guid == company_guid:
            existing.label = label or existing.label
            existing.base_url = url
            existing.company_name = company_name or existing.company_name
            save_destinations(store, destinations)
            return existing
    key = hashlib.sha256(f"{url.lower()}:{company_guid}".encode()).hexdigest()[:16]
    item = Destination(
        id=(destination_id or (f"{slug_from_url(url)}-{key}" if company_guid else slug_from_url(url))),
        label=label or slug_from_url(url),
        base_url=url,
        company_guid=company_guid,
        company_name=company_name,
    )
    destinations.append(item)
    save_destinations(store, destinations)
    return item


def paired_destinations(store: LocalStore, data_dir: Path) -> list[tuple[Destination, str]]:
    paired: list[tuple[Destination, str]] = []
    for destination in list_destinations(store):
        token = load_token(destination.token_path(data_dir))
        if token:
            paired.append((destination, token))
    return paired


def migrate_legacy_destination(store: LocalStore, data_dir: Path, legacy_url: str, legacy_token_path: Path) -> None:
    """Promote the original single-host token into the destinations list."""
    if list_destinations(store):
        return
    token = load_token(legacy_token_path)
    if not token:
        return
    from agent.product import DESTINATION_ID, DESTINATION_LABEL

    destination = upsert_destination(
        store,
        label=DESTINATION_LABEL,
        base_url=legacy_url,
        destination_id=DESTINATION_ID,
    )
    save_token(destination.token_path(data_dir), token)
    if store.get_meta("initial_import_done"):
        store.set_meta(f"import_done_{destination.id}", True)


def import_done(store: LocalStore, destination_id: str, company_guid: str = "") -> bool:
    if company_guid:
        return bool(store.get_meta(f"import_done_{destination_id}_{company_guid}"))
    return bool(store.get_meta(f"import_done_{destination_id}"))


def set_import_done(store: LocalStore, destination_id: str, done: bool = True, company_guid: str = "") -> None:
    if company_guid:
        store.set_meta(f"import_done_{destination_id}_{company_guid}", done)
        if not done:
            store.set_meta(f"import_done_{destination_id}", False)
        return
    store.set_meta(f"import_done_{destination_id}", done)


def is_pluschwood(destination: Destination) -> bool:
    host = urlparse(destination.base_url).netloc.lower()
    return "pluschwood" in host or destination.id.startswith("pluschwood") or "pluschwood" in destination.label.lower()


def cursor_key(destination_id: str, collection: str, company_guid: str = "") -> str:
    if company_guid:
        return f"import_cursor_{destination_id}_{company_guid}_{collection.lower()}"
    return f"import_cursor_{destination_id}_{collection.lower()}"


def get_cursor(store: LocalStore, destination_id: str, collection: str, company_guid: str = "") -> int:
    scoped = int(store.get_meta(cursor_key(destination_id, collection, company_guid), 0) or 0)
    if company_guid and scoped == 0:
        # Fall back to legacy destination-wide cursor once when migrating.
        return int(store.get_meta(cursor_key(destination_id, collection), 0) or 0)
    return scoped


def set_cursor(store: LocalStore, destination_id: str, collection: str, value: int, company_guid: str = "") -> None:
    store.set_meta(cursor_key(destination_id, collection, company_guid), int(value))


def reset_import(store: LocalStore, destination_id: str, company_guids: list[str] | None = None) -> None:
    """Replay import for one destination without touching other destinations' cursors."""
    set_import_done(store, destination_id, False)
    collections = ("group", "ledger", "unit", "godown", "stockgroup", "stockitem", "vouchertype", "voucher")
    for collection in collections:
        set_cursor(store, destination_id, collection, 0)
        for guid in company_guids or []:
            set_cursor(store, destination_id, collection, 0, company_guid=guid)
            set_import_done(store, destination_id, False, company_guid=guid)


def status_summary(store: LocalStore, data_dir: Path) -> str:
    paired = paired_destinations(store, data_dir)
    if not paired:
        return "no destinations"
    labels = []
    for destination, _token in paired:
        mark = "✓" if import_done(store, destination.id) else "…"
        labels.append(f"{destination.label}{mark}")
    return ", ".join(labels)
