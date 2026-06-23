from app import database
from app.skills.base import SkillContext, SkillDefinition


class HelpSkill:
    definition = SkillDefinition(
        key="help",
        title="Ayuda",
        description="Muestra los comandos disponibles.",
        command="ayuda",
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
            lines.append(f"/{skill['command']} - {skill['title']}")
        await context.message.answer("\n".join(lines))


class StatusSkill:
    definition = SkillDefinition(
        key="status",
        title="Estado",
        description="Muestra el estado basico del bot.",
        command="estado",
        messages={
            "status": {
                "label": "Mensaje de estado",
                "default": "AguacatIA activo.\nTu nivel: {level}",
            },
        },
    )

    async def handle(self, context: SkillContext) -> None:
        user = database.get_user_with_level(str(context.message.from_user.id))
        level = user["level_name"] if user else "Publico"
        template = database.get_skill_message(self.definition.key, "status", "AguacatIA activo.\nTu nivel: {level}")
        await context.message.answer(template.format(level=level))
