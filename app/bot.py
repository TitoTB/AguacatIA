import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import BotCommand, Message

from app import database
from app.permissions import can_use_skill
from app.skills import build_registry
from app.skills.base import SkillContext


logger = logging.getLogger(__name__)


class TelegramBotService:
    def __init__(self) -> None:
        self.registry = build_registry()
        self._task: asyncio.Task | None = None
        self._token: str = ""
        self._running = False

    def sync_skills(self) -> None:
        database.sync_skills(definition.__dict__ for definition in self.registry.definitions())

    async def supervise(self) -> None:
        self.sync_skills()
        while True:
            settings = database.settings_map()
            enabled = settings.get("bot_enabled") == "1"
            token = settings.get("telegram_bot_token", "").strip()
            if enabled and token and (not self._task or self._task.done() or token != self._token):
                await self.stop()
                self._token = token
                self._task = asyncio.create_task(self._run_polling(token))
            if (not enabled or not token) and self._task:
                await self.stop()
            await asyncio.sleep(5)

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    async def _run_polling(self, token: str) -> None:
        bot = Bot(token)
        dispatcher = Dispatcher()
        self._register_handlers(dispatcher)
        await self._set_commands(bot)
        self._running = True
        logger.info("AguacatIA Telegram polling started")
        try:
            await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
        finally:
            self._running = False
            await bot.session.close()

    async def _set_commands(self, bot: Bot) -> None:
        skills = database.list_skills()
        commands = [
            BotCommand(command=row["command"], description=row["title"][:256])
            for row in skills
            if row["enabled"] and row["command"]
        ]
        if commands:
            await bot.set_my_commands(commands)

    def _register_handlers(self, dispatcher: Dispatcher) -> None:
        @dispatcher.message(CommandStart())
        async def start(message: Message) -> None:
            display_name = _display_name(message)
            database.ensure_user(str(message.from_user.id), display_name)
            await message.answer("Hola, soy AguacatIA. Usa /ayuda para ver los comandos disponibles.")

        @dispatcher.message(F.text.startswith("/"))
        async def command(message: Message) -> None:
            display_name = _display_name(message)
            telegram_id = str(message.from_user.id)
            database.ensure_user(telegram_id, display_name)
            text = message.text or ""
            raw_command, _, args = text.partition(" ")
            command_name = raw_command.split("@", 1)[0].lstrip("/")
            skill_row = database.get_skill_by_command(command_name)
            skill = self.registry.get(skill_row["key"]) if skill_row else self.registry.get_by_command(command_name)
            if not skill:
                await message.answer("No conozco ese comando. Usa /ayuda.")
                return
            allowed, reason = can_use_skill(telegram_id, skill.definition.key)
            if not allowed:
                database.log_command(telegram_id, skill.definition.key, command_name, "denied", reason)
                await message.answer(reason)
                return
            try:
                await skill.handle(SkillContext(message=message, args=args))
                database.log_command(telegram_id, skill.definition.key, command_name, "ok")
            except Exception as exc:
                logger.exception("Skill failed: %s", skill.definition.key)
                database.log_command(telegram_id, skill.definition.key, command_name, "error", str(exc))
                await message.answer("Ha ocurrido un error ejecutando el comando.")

        @dispatcher.message()
        async def fallback(message: Message) -> None:
            database.ensure_user(str(message.from_user.id), _display_name(message))
            await message.answer("Trabajamos por comandos. Usa /ayuda.")


def _display_name(message: Message) -> str:
    user = message.from_user
    if not user:
        return ""
    bits = [user.first_name or "", user.last_name or ""]
    name = " ".join(bit for bit in bits if bit).strip()
    if user.username:
        name = f"{name} (@{user.username})" if name else f"@{user.username}"
    return name
