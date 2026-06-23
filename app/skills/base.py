from dataclasses import dataclass
from typing import Protocol

from aiogram.types import Message


@dataclass(frozen=True)
class SkillDefinition:
    key: str
    title: str
    description: str
    command: str


@dataclass
class SkillContext:
    message: Message
    args: str


class Skill(Protocol):
    definition: SkillDefinition

    async def handle(self, context: SkillContext) -> None:
        ...

