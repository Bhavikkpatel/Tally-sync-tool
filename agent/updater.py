from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx

from agent.version import GITHUB_RELEASES_API, GITHUB_RELEASES_URL, __version__


@dataclass
class UpdateInfo:
    current_version: str
    latest_version: str
    update_available: bool
    release_url: str
    release_notes: str
    asset_name: str | None = None
    asset_url: str | None = None
    message: str = ""


def _parse_version(value: str) -> tuple[int, ...]:
    cleaned = (value or "").strip().lstrip("vV")
    parts = re.findall(r"\d+", cleaned)
    if not parts:
        return (0,)
    return tuple(int(part) for part in parts)


def is_newer(latest: str, current: str) -> bool:
    left = _parse_version(latest)
    right = _parse_version(current)
    width = max(len(left), len(right))
    left = left + (0,) * (width - len(left))
    right = right + (0,) * (width - len(right))
    return left > right


def _pick_installer_asset(assets: list[dict[str, Any]]) -> dict[str, Any] | None:
    preferred = []
    for asset in assets or []:
        name = str(asset.get("name") or "").lower()
        if name.endswith(".exe") or name.endswith(".msi"):
            preferred.append(asset)
    if not preferred:
        return None
    for asset in preferred:
        name = str(asset.get("name") or "").lower()
        if "setup" in name or "installer" in name:
            return asset
    return preferred[0]


def check_for_update(timeout: float = 20.0) -> UpdateInfo:
    current = __version__
    try:
        response = httpx.get(
            GITHUB_RELEASES_API,
            headers={"Accept": "application/vnd.github+json", "User-Agent": f"TallySync/{current}"},
            timeout=timeout,
            follow_redirects=True,
        )
    except httpx.HTTPError as exc:
        return UpdateInfo(
            current_version=current,
            latest_version=current,
            update_available=False,
            release_url=GITHUB_RELEASES_URL,
            release_notes="",
            message=f"Could not reach GitHub: {exc}",
        )
    if response.status_code == 404:
        return UpdateInfo(
            current_version=current,
            latest_version=current,
            update_available=False,
            release_url=GITHUB_RELEASES_URL,
            release_notes="",
            message="No GitHub releases published yet.",
        )
    if response.status_code >= 400:
        return UpdateInfo(
            current_version=current,
            latest_version=current,
            update_available=False,
            release_url=GITHUB_RELEASES_URL,
            release_notes="",
            message=f"GitHub returned HTTP {response.status_code}",
        )
    payload = response.json()
    tag = str(payload.get("tag_name") or payload.get("name") or "").strip()
    latest = tag.lstrip("vV") or current
    asset = _pick_installer_asset(payload.get("assets") or [])
    available = is_newer(latest, current)
    return UpdateInfo(
        current_version=current,
        latest_version=latest,
        update_available=available,
        release_url=str(payload.get("html_url") or GITHUB_RELEASES_URL),
        release_notes=str(payload.get("body") or "").strip(),
        asset_name=(asset or {}).get("name"),
        asset_url=(asset or {}).get("browser_download_url"),
        message=("Update available" if available else "You are on the latest version"),
    )
