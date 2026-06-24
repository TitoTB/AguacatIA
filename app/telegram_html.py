from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message


def _is_html_parse_error(exc: TelegramBadRequest) -> bool:
    return "can't parse entities" in str(exc).lower()


async def answer_html(message: Message, text: str, **kwargs) -> None:
    try:
        await message.answer(text, parse_mode="HTML", **kwargs)
    except TelegramBadRequest as exc:
        if not _is_html_parse_error(exc):
            raise
        await message.answer(text, **kwargs)


async def answer_photo_html(message: Message, photo: str, caption: str, **kwargs) -> None:
    try:
        await message.answer_photo(photo=photo, caption=caption, parse_mode="HTML", **kwargs)
    except TelegramBadRequest as exc:
        if not _is_html_parse_error(exc):
            raise
        await message.answer_photo(photo=photo, caption=caption, **kwargs)
