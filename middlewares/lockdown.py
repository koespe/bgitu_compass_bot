import json
from pathlib import Path
from typing import Callable, Awaitable, Dict, Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from cachetools import cached, TTLCache

from config_reader import graphics, config
from database.base import DB

LOCKDOWN_MESSAGE = (
    "\U0001F6A7 Расписание на новый учебный год ещё не опубликовано.\n"
    "<b>Бот пришлет уведомление при появлении групп.</b>\n\n"
    "\U0001f49a У нас есть <b>приложение для Android</b>:\n"
    "\u2192 compass.bgitu.ru"
)
LOCKDOWN_FILE = Path("data") / "lockdown.json"

lockdown_cache = TTLCache(maxsize=1, ttl=300)


def read_lockdown_state() -> dict:
    if not LOCKDOWN_FILE.exists():
        return {}
    try:
        with open(LOCKDOWN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def write_lockdown_state(state: dict) -> None:
    LOCKDOWN_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCKDOWN_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)


@cached(lockdown_cache)
def is_lockdown_active() -> bool:
    return read_lockdown_state().get("active", False)


class LockdownMiddleware(BaseMiddleware):
    async def __call__(
            self,
            handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: Dict[str, Any],
    ) -> Any:
        if not is_lockdown_active():
            return await handler(event, data)

        if event.from_user.id == config.admin_tg_id:
            await event.answer("LOCKDOWN активен.")
            return await handler(event, data)  # Доступ к команде /admin

        if isinstance(event, Message):
            await event.answer_photo(photo=graphics.start_menu)
            await event.answer(LOCKDOWN_MESSAGE)
            await DB.add_user(user_id=event.from_user.id)
        elif isinstance(event, CallbackQuery):
            await event.message.answer_photo(photo=graphics.start_menu)
            await event.message.answer(LOCKDOWN_MESSAGE)
            await DB.add_user(user_id=event.from_user.id)

        return None
