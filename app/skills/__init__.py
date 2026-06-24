from app.skills.bdevices import BDevicesSearchSkill
from app.skills.builtin import BotSystemSkill, HelpSkill, StatusSkill
from app.skills.registry import SkillRegistry


def build_registry() -> SkillRegistry:
    registry = SkillRegistry()
    registry.register(BotSystemSkill())
    registry.register(HelpSkill())
    registry.register(StatusSkill())
    registry.register(BDevicesSearchSkill())
    return registry
