import json
from pathlib import Path
from typing import Callable, Awaitable, Dict, Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from cachetools import cached, TTLCache

from config_reader import graphics

LOCKDOWN_FILE = Path("data") / "lockdown.json"

lockdown_cache = TTLCache(maxsize=1, ttl=300)


@cached(lockdown_cache)
def is_lockdown_active() -> bool:
    if not LOCKDOWN_FILE.exists():
        return False

    with open(LOCKDOWN_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        return data.get("active", False)


LOCKDOWN_MESSAGE = (
    "\U0001F6A7 Расписание на новый учебный год ещё не опубликовано.\n"
    "<b>Бот пришлет уведомление при появлении групп.</b>\n\n"
    "\U0001f49a У нас есть <b>приложение для Android</b>:\n"
    "\u2192 bgitu-compass.ru"
)


class LockdownMiddleware(BaseMiddleware):
    async def __call__(
            self,
            handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: Dict[str, Any],
    ) -> Any:
        if not is_lockdown_active():
            return await handler(event, data)

        if isinstance(event, Message):
            await event.answer_photo(photo=graphics.start_menu)
            await event.answer(LOCKDOWN_MESSAGE)
        elif isinstance(event, CallbackQuery):
            await event.message.answer_photo(photo=graphics.start_menu)
            await event.message.answer(LOCKDOWN_MESSAGE)

        return None
