import html

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
        skills = [row for row in database.list_skills() if row["enabled"]]
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
