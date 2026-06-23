import html

import httpx

from app import database
from app.skills.base import SkillContext, SkillDefinition


class BDevicesSearchSkill:
    definition = SkillDefinition(
        key="bdevices_search",
        title="Buscar dispositivo BDevices",
        description="Consulta la API de BDevices para recomendar dispositivos de domotica.",
        command="dispositivo",
    )

    async def handle(self, context: SkillContext) -> None:
        query = context.args.strip()
        if not query:
            await context.message.answer("Usa: /dispositivo sensor temperatura zigbee")
            return

        settings = database.settings_map()
        url = settings.get("bdevices_search_url", "").strip()
        if not url:
            await context.message.answer("La URL de BDevices no esta configurada.")
            return

        headers = {}
        token = settings.get("bdevices_agent_token", "").strip()
        if token:
            headers["X-BDevices-Agent-Token"] = token

        payload = {"query": query, "limit": 5, "require_price": False}
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            await context.message.answer(f"BDevices ha respondido con error {exc.response.status_code}.")
            return
        except Exception as exc:
            await context.message.answer(f"No he podido consultar BDevices: {exc}")
            return

        results = data.get("results") or []
        if not results:
            await context.message.answer("No he encontrado dispositivos para esa consulta.")
            return

        lines = [f"Resultados para: <b>{html.escape(query)}</b>"]
        for index, item in enumerate(results[:5], start=1):
            title = item.get("title") or item.get("name") or "Dispositivo"
            brand = item.get("brand") or ""
            categories = item.get("categories") or []
            category = item.get("category") or (", ".join(categories) if isinstance(categories, list) else "")
            best = item.get("best_option") or {}
            options = item.get("shopping_options") or item.get("options") or []
            if not best and options:
                best = _best_option(options)
            price = _format_price(
                best.get("price") if best else item.get("best_price"),
                (best.get("currency") if best else None) or item.get("currency") or "EUR",
            )
            url = (best.get("url") if best else "") or item.get("best_url") or item.get("url") or ""
            meta = " · ".join(value for value in [brand, category] if value)
            suffix = f"\n   {html.escape(meta)}" if meta else ""
            price_line = f"\n   Mejor precio: {html.escape(price)}" if price else ""
            url_line = f"\n   {html.escape(url)}" if url else ""
            lines.append(f"\n{index}. <b>{html.escape(str(title))}</b>{suffix}{price_line}{url_line}")

        await context.message.answer("\n".join(lines), parse_mode="HTML", disable_web_page_preview=True)


def _format_price(value: object, currency: str) -> str:
    if value is None or value == "":
        return ""
    try:
        return f"{float(value):.2f} {currency}"
    except (TypeError, ValueError):
        return f"{value} {currency}"


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
