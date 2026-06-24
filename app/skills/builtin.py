import asyncio
import html

from aiogram.exceptions import TelegramBadRequest

from app import database
from app.skills.base import SkillContext, SkillDefinition
from app.telegram_html import answer_html


class HelpSkill:
    definition = SkillDefinition(
        key="help",
        title="Ayuda",
        description="Muestra los comandos disponibles.",
        command="ayuda",
        variables={},
        messages={
            "header": {
                "label": "Cabecera de ayuda",
                "default": "Comandos disponibles:",
            },
        },
    )

    async def handle(self, context: SkillContext) -> None:
        skills = [row for row in database.list_skills() if row["enabled"] and row["command"]]
        lines = [database.get_skill_message(self.definition.key, "header", "Comandos disponibles:")]
        for skill in skills:
            lines.append(f"/{html.escape(str(skill['command']))} - {html.escape(str(skill['title']))}")
        await answer_html(context.message, "\n".join(lines))


class StatusSkill:
    definition = SkillDefinition(
        key="status",
        title="Estado",
        description="Muestra el estado basico del bot.",
        command="estado",
        variables={
            "level": "Nivel del usuario",
        },
        messages={
            "status": {
                "label": "Mensaje de estado",
                "default": "AguacatIA activo.\nTu nivel: {level}",
            },
        },
    )

    async def handle(self, context: SkillContext) -> None:
        user = database.get_user_with_level(str(context.message.from_user.id))
        level = html.escape(str(user["level_name"] if user else "Publico"))
        template = database.get_skill_message(self.definition.key, "status", "AguacatIA activo.\nTu nivel: {level}")
        await answer_html(context.message, template.format(level=level))


class CleanChatSkill:
    definition = SkillDefinition(
        key="clean_chat",
        title="Limpiar chat",
        description="Borra mensajes recientes del chat cuando Telegram lo permite.",
        command="limpiar",
        variables={
            "count": "Numero de mensajes solicitados",
            "deleted": "Numero de mensajes borrados",
        },
        messages={
            "nothing_deleted": {
                "label": "Mensaje si no puede borrar",
                "default": "No he podido borrar mensajes recientes en este chat.",
            },
            "confirmation": {
                "label": "Confirmacion temporal",
                "default": "Chat limpiado: {deleted} mensajes.",
            },
        },
    )

    async def handle(self, context: SkillContext) -> None:
        count = _clean_count(context.args)
        deleted = 0
        chat_id = context.message.chat.id
        first_message_id = context.message.message_id
        for message_id in range(first_message_id, max(first_message_id - count, 0), -1):
            try:
                await context.message.bot.delete_message(chat_id=chat_id, message_id=message_id)
                deleted += 1
            except TelegramBadRequest:
                continue

        values = {"count": html.escape(str(count)), "deleted": html.escape(str(deleted))}
        if deleted == 0:
            await answer_html(
                context.message,
                database.get_skill_message(self.definition.key, "nothing_deleted", self.definition.messages["nothing_deleted"]["default"]).format_map(_SafeValues(values)),
            )
            return

        template = database.get_skill_message(self.definition.key, "confirmation", self.definition.messages["confirmation"]["default"])
        try:
            confirmation = await context.message.answer(template.format_map(_SafeValues(values)), parse_mode="HTML")
        except TelegramBadRequest:
            confirmation = await context.message.answer(template.format_map(_SafeValues(values)))
        await asyncio.sleep(3)
        try:
            await context.message.bot.delete_message(chat_id=chat_id, message_id=confirmation.message_id)
        except TelegramBadRequest:
            pass


class BotSystemSkill:
    definition = SkillDefinition(
        key="bot_system",
        title="Sistema del bot",
        description="Mensajes generales de Telegram que no pertenecen a una skill concreta.",
        command="",
        variables={},
        messages={
            "start": {
                "label": "Mensaje /start",
                "default": "Hola, soy AguacatIA. Usa /ayuda para ver los comandos disponibles.",
            },
            "fallback": {
                "label": "Mensaje sin comando",
                "default": "Trabajamos por comandos. Usa /ayuda.",
            },
            "unknown_command": {
                "label": "Comando desconocido",
                "default": "No conozco ese comando. Usa /ayuda.",
            },
            "skill_error": {
                "label": "Error ejecutando skill",
                "default": "Ha ocurrido un error ejecutando el comando.",
            },
        },
    )

    async def handle(self, context: SkillContext) -> None:
        await answer_html(context.message, database.get_skill_message(self.definition.key, "fallback", "Trabajamos por comandos. Usa /ayuda."))


def _clean_count(args: str) -> int:
    try:
        count = int((args or "").strip() or "30")
    except ValueError:
        count = 30
    return min(max(count, 1), 100)


class _SafeValues(dict):
    def __missing__(self, key):
        return ""
