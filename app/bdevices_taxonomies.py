import asyncio
from urllib.parse import urlsplit, urlunsplit

import httpx

from app import database


SYNC_INTERVAL_SECONDS = 60 * 60 * 24
TAXONOMY_KEYS = {
    "brands": "brand",
    "brand": "brand",
    "categories": "category",
    "category": "category",
    "protocols": "protocol",
    "protocol": "protocol",
    "integration_types": "integration_type",
    "integration_type": "integration_type",
    "marketplaces": "marketplace",
    "marketplace": "marketplace",
    "battery": "battery",
    "local_function": "local_function",
}


async def sync_once() -> tuple[bool, str]:
    settings = database.settings_map()
    url = _taxonomies_url(settings)
    if not url:
        return _record(False, "URL de taxonomias BDevices sin configurar")

    headers = {}
    token = settings.get("bdevices_agent_token", "").strip()
    if token:
        headers["X-BDevices-Agent-Token"] = token

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        return _record(False, f"HTTP {exc.response.status_code} al sincronizar taxonomias")
    except Exception as exc:
        return _record(False, f"Error sincronizando taxonomias: {exc}")

    taxonomies = _parse_payload(payload)
    if not taxonomies:
        return _record(False, "BDevices no devolvio taxonomias reconocibles")

    count = database.replace_bdevices_taxonomies(taxonomies)
    return _record(True, f"Taxonomias sincronizadas: {count} valores")


async def periodic_sync() -> None:
    while True:
        await sync_once()
        await asyncio.sleep(SYNC_INTERVAL_SECONDS)


def _taxonomies_url(settings: dict[str, str]) -> str:
    configured = settings.get("bdevices_taxonomies_url", "").strip()
    if configured:
        return configured
    search_url = settings.get("bdevices_search_url", "").strip()
    if not search_url:
        return ""
    split = urlsplit(search_url)
    path = split.path.rstrip("/")
    if path.endswith("/search"):
        path = path[: -len("/search")]
    path = f"{path}/taxonomies"
    return urlunsplit((split.scheme, split.netloc, path, "", ""))


def _parse_payload(payload: object) -> dict[str, list[str]]:
    if not isinstance(payload, dict):
        return {}
    source = payload.get("taxonomies") if isinstance(payload.get("taxonomies"), dict) else payload
    taxonomies: dict[str, list[str]] = {}
    for raw_key, values in source.items():
        key = TAXONOMY_KEYS.get(str(raw_key))
        if not key:
            continue
        taxonomies[key] = _string_values(values)
    return {key: values for key, values in taxonomies.items() if values}


def _string_values(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    result = []
    for value in values:
        if isinstance(value, dict):
            value = value.get("name") or value.get("value") or value.get("label")
        text = str(value or "").strip()
        if text:
            result.append(text)
    return sorted(set(result), key=str.lower)


def _record(ok: bool, status: str) -> tuple[bool, str]:
    database.save_setting("bdevices_taxonomies_last_sync", database.utc_now())
    database.save_setting("bdevices_taxonomies_last_status", status)
    return ok, status
