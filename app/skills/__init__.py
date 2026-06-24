from app.skills.bdevices import BDevicesSearchSkill
from app.skills.builtin import BotSystemSkill, CleanChatSkill, HelpSkill, StatusSkill
from app.skills.registry import SkillRegistry


def build_registry() -> SkillRegistry:
    registry = SkillRegistry()
    registry.register(BotSystemSkill())
    registry.register(HelpSkill())
    registry.register(StatusSkill())
    registry.register(CleanChatSkill())
    registry.register(BDevicesSearchSkill())
    return registry
