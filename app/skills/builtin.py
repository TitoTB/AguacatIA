from app import database
from app.skills.base import SkillContext, SkillDefinition


class HelpSkill:
    definition = SkillDefinition(
        key="help",
        title="Ayuda",
        description="Muestra los comandos disponibles.",
        command="ayuda",
    )

    async def handle(self, context: SkillContext) -> None:
        skills = [row for row in database.list_skills() if row["enabled"]]
        lines = ["Comandos disponibles:"]
        for skill in skills:
            lines.append(f"/{skill['command']} - {skill['title']}")
        await context.message.answer("\n".join(lines))


class StatusSkill:
    definition = SkillDefinition(
        key="status",
        title="Estado",
        description="Muestra el estado basico del bot.",
        command="estado",
    )

    async def handle(self, context: SkillContext) -> None:
        user = database.get_user_with_level(str(context.message.from_user.id))
        level = user["level_name"] if user else "Publico"
        await context.message.answer(f"AguacatIA activo.\nTu nivel: {level}")

