from app.skills.base import Skill, SkillDefinition


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}
        self._commands: dict[str, str] = {}

    def register(self, skill: Skill) -> None:
        self._skills[skill.definition.key] = skill
        self._commands[skill.definition.command] = skill.definition.key

    def get(self, key: str) -> Skill | None:
        return self._skills.get(key)

    def get_by_command(self, command: str) -> Skill | None:
        key = self._commands.get(command)
        return self._skills.get(key or "")

    def definitions(self) -> list[SkillDefinition]:
        return [skill.definition for skill in self._skills.values()]

