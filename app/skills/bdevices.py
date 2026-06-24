import html
import json
import re
import unicodedata

import httpx
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app import database
from app.skills.base import SkillContext, SkillDefinition


class BDevicesSearchSkill:
    definition = SkillDefinition(
        key="bdevices_search",
        title="Buscar dispositivo BDevices",
        description="Consulta la API de BDevices para recomendar dispositivos de domotica.",
        command="dispositivo",
        triggers=[
            "busca un dispositivo",
            "buscar dispositivo",
            "recomiendame un dispositivo",
            "recomienda un dispositivo",
            "quiero un dispositivo",
            "busco un dispositivo",
            "busco un sensor",
            "recomiendame un sensor",
        ],
        messages={
            "empty_query": {
                "label": "Mensaje sin consulta",
                "default": "Usa: /{command} sensor temperatura zigbee",
            },
            "missing_config": {
                "label": "Mensaje sin configuracion",
                "default": "La URL de BDevices no esta configurada.",
            },
            "no_results": {
                "label": "Mensaje sin resultados",
                "default": "No he encontrado dispositivos para esa consulta.",
            },
            "http_error": {
                "label": "Error HTTP BDevices",
                "default": "BDevices ha respondido con error {status_code}.",
            },
            "request_error": {
                "label": "Error de consulta BDevices",
                "default": "No he podido consultar BDevices: {error}",
            },
            "caption_template": {
                "label": "Caption de resultado",
                "default": "<b>{name}</b>\n\n{description}\n\n<b>Caracteristicas</b>\nMarca: {brand}\nCategorias: {categories}\nProtocolos: {protocols}\nIntegracion: {integration_type}\nFuncion: {local_function}\nBateria: {battery}\nDificultad: {difficulty}\nRating: {rating}\n\n<b>Precio:</b> {price}",
            },
            "button_text": {
                "label": "Texto del boton",
                "default": "IR A LA OFERTA",
            },
            "fallback_image_message": {
                "label": "Mensaje si no hay imagen",
                "default": "No he encontrado imagen para este dispositivo.",
            },
            "ai_query_prompt": {
                "label": "Prompt IA para interpretar consulta",
                "default": "Convierte la consulta del usuario en filtros JSON para buscar dispositivos de domotica. Devuelve solo JSON valido con estas claves opcionales: query, brand, category, protocol, integration_type, marketplace, max_price, min_rating, local_function, battery, sort. Usa solo valores presentes en estas taxonomias cuando existan:\n{taxonomies}\nValores especiales: local_function y battery deben ser Si o No; sort debe ser relevance, price_asc, price_desc o rating_desc. No inventes valores. Consulta: {query}",
            },
        },
    )

    async def handle(self, context: SkillContext) -> None:
        query = context.args.strip()
        skill_row = database.get_skill(self.definition.key)
        command = skill_row["command"] if skill_row else self.definition.command
        if not query:
            await context.message.answer(_render_template(_message(self.definition.key, "empty_query"), {"command": command}))
            return

        settings = database.settings_map()
        url = settings.get("bdevices_search_url", "").strip()
        if not url:
            await context.message.answer(_message(self.definition.key, "missing_config"))
            return

        headers = {}
        token = settings.get("bdevices_agent_token", "").strip()
        if token:
            headers["X-BDevices-Agent-Token"] = token

        payload = await _build_search_payload(query, settings)
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            await context.message.answer(
                _render_template(_message(self.definition.key, "http_error"), {"status_code": exc.response.status_code})
            )
            return
        except Exception as exc:
            await context.message.answer(_render_template(_message(self.definition.key, "request_error"), {"error": exc}))
            return

        results = data.get("results") or []
        if not results:
            await context.message.answer(_message(self.definition.key, "no_results"))
            return

        for item in results[:1]:
            await _send_device_result(context, item)


async def _build_search_payload(query: str, settings: dict[str, str]) -> dict:
    payload = _local_query_payload(query)
    if _should_use_ai_query_parser(settings, payload):
        ai_payload = await _ollama_query_payload(query, settings)
        payload = _merge_payloads(payload, ai_payload)
    payload["query"] = payload.get("query") or query
    payload["limit"] = 1
    payload["require_price"] = False
    return _clean_payload(payload)


def _local_query_payload(query: str) -> dict:
    normalized = _normalize(query)
    payload: dict[str, object] = {"query": query, "sort": "relevance"}
    taxonomies = database.bdevices_taxonomies_normalized_map()

    brand = _match_taxonomy(normalized, taxonomies.get("brand", {}))
    if brand:
        payload["brand"] = brand
    else:
        for brand in _BRANDS:
            if _contains_term(normalized, brand):
                payload["brand"] = brand
                break

    protocol = _match_taxonomy(normalized, taxonomies.get("protocol", {}))
    if protocol:
        payload["protocol"] = protocol
    else:
        for protocol, terms in _PROTOCOL_TERMS.items():
            if any(_contains_term(normalized, term) for term in terms):
                payload["protocol"] = protocol
                break

    category = _match_taxonomy(normalized, taxonomies.get("category", {}))
    if category:
        payload["category"] = category

    integration_type = _match_taxonomy(normalized, taxonomies.get("integration_type", {}))
    if integration_type:
        payload["integration_type"] = integration_type

    if any(term in normalized for term in ["local", "localmente", "sin nube", "sin cloud"]):
        payload["local_function"] = "Si"
    elif any(term in normalized for term in ["nube", "cloud"]):
        payload["local_function"] = "No"

    marketplace = _match_taxonomy(normalized, taxonomies.get("marketplace", {}))
    if marketplace:
        payload["marketplace"] = marketplace
    else:
        for marketplace, terms in _MARKETPLACE_TERMS.items():
            if any(_contains_term(normalized, term) for term in terms):
                payload["marketplace"] = marketplace
                break

    if any(term in normalized for term in ["enchufado", "corriente", "sin bateria", "sin pilas"]):
        payload["battery"] = "No"
    elif any(term in normalized for term in ["bateria", "pilas", "pila", "inalambrico"]):
        payload["battery"] = "Si"

    max_price = _extract_max_price(normalized)
    if max_price is not None:
        payload["max_price"] = max_price

    min_rating = _extract_min_rating(normalized)
    if min_rating is not None:
        payload["min_rating"] = min_rating

    if any(term in normalized for term in ["mejor valorado", "mejor valorada", "rating", "valoracion"]):
        payload["sort"] = "rating_desc"
    elif any(term in normalized for term in ["barato", "barata", "mas barato", "mejor precio", "economico"]):
        payload["sort"] = "price_asc"
    elif any(term in normalized for term in ["mejor", "recomendado", "calidad"]):
        payload["sort"] = "relevance"

    return payload


def _should_use_ai_query_parser(settings: dict[str, str], payload: dict) -> bool:
    if settings.get("bdevices_ai_query_enabled") != "1":
        return False
    if settings.get("ai_provider") != "ollama":
        return False
    if not settings.get("ollama_base_url", "").strip():
        return False
    detected_filters = {key for key in payload if key not in {"query", "limit", "require_price", "sort"}}
    return len(detected_filters) < 2


async def _ollama_query_payload(query: str, settings: dict[str, str]) -> dict:
    base_url = settings.get("ollama_base_url", "").rstrip("/")
    model = settings.get("ollama_model", "").strip() or "llama3.1"
    prompt = _render_template(
        _message(BDevicesSearchSkill.definition.key, "ai_query_prompt"),
        {"query": query, "taxonomies": _taxonomy_prompt_context()},
    )
    try:
        async with httpx.AsyncClient(timeout=18) as client:
            response = await client.post(
                f"{base_url}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False, "format": "json"},
            )
            response.raise_for_status()
            data = response.json()
    except Exception:
        return {}
    content = str(data.get("response") or "").strip()
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {key: value for key, value in parsed.items() if key in _ALLOWED_PAYLOAD_KEYS}


def _merge_payloads(local_payload: dict, ai_payload: dict) -> dict:
    merged = dict(local_payload)
    for key, value in ai_payload.items():
        if value in (None, "", [], {}):
            continue
        if key == "query" and merged.get("query"):
            continue
        merged[key] = value
    return merged


def _clean_payload(payload: dict) -> dict:
    cleaned = {}
    for key, value in payload.items():
        if key not in _ALLOWED_PAYLOAD_KEYS:
            continue
        if value in (None, "", [], {}):
            continue
        if key in {"max_price", "min_rating"}:
            try:
                cleaned[key] = float(value)
            except (TypeError, ValueError):
                continue
        elif key == "limit":
            cleaned[key] = max(1, min(int(value), 20))
        elif key == "require_price":
            cleaned[key] = bool(value)
        else:
            cleaned[key] = _normalize_payload_value(key, value)
    return cleaned


def _normalize_payload_value(key: str, value: object) -> str:
    text = str(value).strip()
    normalized = _normalize(text)
    if key == "protocol":
        return _PROTOCOL_ALIASES.get(normalized, text)
    if key in {"battery", "local_function"}:
        if normalized in {"si", "yes", "true", "con bateria", "bateria", "local"}:
            return "Si"
        if normalized in {"no", "false", "sin bateria", "sin pilas", "nube", "cloud"}:
            return "No"
    if key == "sort":
        return {
            "price": "price_asc",
            "barato": "price_asc",
            "cheap": "price_asc",
            "rating": "rating_desc",
            "mejor valorado": "rating_desc",
        }.get(normalized, text)
    return text


async def _send_device_result(context: SkillContext, item: dict) -> None:
    values = _device_values(item)
    caption = _render_template(_message(BDevicesSearchSkill.definition.key, "caption_template"), values)
    keyboard = None
    if values["best_url"]:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=_message(BDevicesSearchSkill.definition.key, "button_text"),
                        url=values["best_url"],
                    )
                ],
            ]
        )
    if values["image"]:
        await context.message.answer_photo(
            photo=values["image"],
            caption=_trim_text(caption, 1024),
            parse_mode="HTML",
            reply_markup=keyboard,
        )
        return

    await context.message.answer(
        f"{_message(BDevicesSearchSkill.definition.key, 'fallback_image_message')}\n\n{_trim_text(caption, 3500)}",
        parse_mode="HTML",
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )


def _device_values(item: dict) -> dict[str, str]:
    best = item.get("best_option") or {}
    options = item.get("shopping_options") or item.get("options") or []
    if not best and options:
        best = _best_option(options)
    currency = (best.get("currency") if best else None) or item.get("currency") or "EUR"
    price = _format_price(best.get("price") if best else item.get("best_price"), currency)
    best_url = (best.get("url") if best else "") or item.get("best_url") or item.get("url") or ""
    return {
        "name": _escape(item.get("title") or item.get("name") or "Dispositivo"),
        "description": _escape(item.get("description") or ""),
        "brand": _escape(item.get("brand") or ""),
        "categories": _escape(_join_list(item.get("categories") or item.get("category"))),
        "protocols": _escape(_join_list(item.get("protocols") or item.get("protocol"))),
        "integration_type": _escape(item.get("integration_type") or ""),
        "local_function": _escape(item.get("local_function") or ""),
        "battery": _escape(item.get("battery") or ""),
        "difficulty": _escape(item.get("difficulty") or ""),
        "rating": _escape(_format_rating(item.get("rating"))),
        "price": _escape(price),
        "best_platform": _escape(item.get("best_platform") or (best.get("label") if best else "") or ""),
        "best_url": str(best_url),
        "image": str(item.get("image") or ""),
    }


def _message(skill_key: str, message_key: str) -> str:
    return database.get_skill_message(skill_key, message_key, "")


def _render_template(template: str, values: dict[str, object]) -> str:
    try:
        return template.format_map(_SafeValues({key: str(value) for key, value in values.items()}))
    except Exception:
        return str(values.get("name", ""))


class _SafeValues(dict):
    def __missing__(self, key):
        return ""


def _escape(value: object) -> str:
    return html.escape(str(value or ""))


def _join_list(value: object) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if item)
    return str(value or "")


def _trim_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "..."


def _format_price(value: object, currency: str) -> str:
    if value is None or value == "":
        return ""
    try:
        return f"{float(value):.2f} {currency}"
    except (TypeError, ValueError):
        return f"{value} {currency}"


def _format_rating(value: object) -> str:
    if value is None or value == "":
        return ""
    try:
        return str(round(float(value)))
    except (TypeError, ValueError):
        return str(value)


def _best_option(options: list[dict]) -> dict:
    priced = [option for option in options if option.get("price") is not None]
    if not priced:
        return options[0] if options else {}
    return min(priced, key=lambda option: _price_sort_value(option.get("price")))


def _price_sort_value(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 999999999.0


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.lower())
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", plain).strip()


def _contains_term(text: str, term: str) -> bool:
    return re.search(rf"(^|\W){re.escape(term)}($|\W)", text) is not None


def _match_taxonomy(text: str, values_by_normalized: dict[str, str]) -> str:
    matches = [
        (normalized, value)
        for normalized, value in values_by_normalized.items()
        if normalized and _contains_term(text, normalized)
    ]
    if not matches:
        return ""
    return max(matches, key=lambda item: len(item[0]))[1]


def _taxonomy_prompt_context() -> str:
    taxonomies = database.bdevices_taxonomies_map()
    if not taxonomies:
        return "No hay taxonomias sincronizadas."
    lines = []
    for key in ["brand", "category", "protocol", "integration_type", "marketplace", "battery", "local_function"]:
        values = taxonomies.get(key, [])[:60]
        if values:
            lines.append(f"{key}: {', '.join(values)}")
    return "\n".join(lines) or "No hay taxonomias sincronizadas."


def _extract_max_price(text: str) -> float | None:
    patterns = [
        r"(?:menos de|hasta|maximo|max|por debajo de)\s*(\d+(?:[\.,]\d+)?)\s*(?:e|eur|euros|€)?",
        r"(\d+(?:[\.,]\d+)?)\s*(?:e|eur|euros|€)\s*(?:o menos|maximo|max)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return float(match.group(1).replace(",", "."))
    return None


def _extract_min_rating(text: str) -> float | None:
    match = re.search(r"(?:rating|valoracion|nota)\s*(?:minima|de)?\s*(\d+(?:[\.,]\d+)?)", text)
    if not match:
        return None
    return float(match.group(1).replace(",", "."))


_ALLOWED_PAYLOAD_KEYS = {
    "query",
    "brand",
    "category",
    "protocol",
    "integration_type",
    "marketplace",
    "max_price",
    "min_rating",
    "local_function",
    "battery",
    "sort",
    "limit",
    "require_price",
}

_BRANDS = [
    "aqara",
    "sonoff",
    "tuya",
    "xiaomi",
    "shelly",
    "ikea",
    "philips",
    "govee",
    "switchbot",
    "meross",
    "broadlink",
    "tapo",
    "tp-link",
    "eufy",
    "reolink",
]

_PROTOCOL_TERMS = {
    "Zigbee": ["zigbee"],
    "WiFi": ["wifi", "wi-fi"],
    "Matter": ["matter"],
    "Thread": ["thread"],
    "Bluetooth": ["bluetooth", "ble"],
    "Z-Wave": ["zwave", "z-wave"],
    "433": ["433", "rf433", "radiofrecuencia"],
    "IR": ["ir", "infrarrojo", "infrarrojos"],
}

_MARKETPLACE_TERMS = {
    "amazon": ["amazon"],
    "aliexpress": ["aliexpress", "ali express"],
    "official": ["oficial", "tienda oficial"],
}

_PROTOCOL_ALIASES = {
    "zigbee": "Zigbee",
    "wifi": "WiFi",
    "wi-fi": "WiFi",
    "matter": "Matter",
    "thread": "Thread",
    "bluetooth": "Bluetooth",
    "ble": "Bluetooth",
    "zwave": "Z-Wave",
    "z-wave": "Z-Wave",
    "433": "433",
    "ir": "IR",
    "infrarrojo": "IR",
}
