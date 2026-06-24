from dataclasses import dataclass, field
from typing import Protocol

from aiogram.types import Message


@dataclass(frozen=True)
class SkillDefinition:
    key: str
    title: str
    description: str
    command: str
    messages: dict[str, dict[str, str]] = field(default_factory=dict)
    triggers: list[str] = field(default_factory=list)


@dataclass
class SkillContext:
    message: Message
    args: str


class Skill(Protocol):
    definition: SkillDefinition

    async def handle(self, context: SkillContext) -> None:
        ...
