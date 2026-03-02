import asyncio
import json
from contextlib import suppress
from pathlib import Path
from typing import Optional

import aiohttp
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import select

from config_reader import config
from database.base import get_session
from database.models import Users
from keyboards import KB

CACHE_FILE = Path("data") / "groups_cache.json"


async def fetch_groups_info() -> list[dict]:
    async with aiohttp.ClientSession() as session:
        response = await session.get(config.api_host + "groupsInfo")
        if response.status == 200:
            return await response.json()
        return []


def load_cached_data() -> Optional[dict[str, dict]]:
    if not CACHE_FILE.exists():
        return None

    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_cached_data(groups: list[dict]) -> None:
    cache_data = {str(group["id"]): group for group in groups}

    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache_data, f, ensure_ascii=False, indent=2)


def get_changed_groups(current_groups: list[dict], cached_data: Optional[dict[str, dict]]) -> list[dict]:
    if cached_data is None:
        return []

    changed = []
    for group in current_groups:
        group_id = str(group["id"])
        old_data = cached_data.get(group_id)

        if old_data is None:
            continue

        old_timestamp = old_data.get("scheduleUpdateDate")
        new_timestamp = group.get("scheduleUpdateDate")

        if old_timestamp != new_timestamp:
            changed.append(group)

    return changed


async def send_schedule_update_notification(bot: Bot, changed_groups: list[dict]) -> None:
    groups_map = {group["id"]: group["name"] for group in changed_groups}
    changed_group_ids = set(groups_map.keys())

    async with get_session() as session:
        query = select(Users.id, Users.group_id, Users.favorite_groups, Users.teacher_name)
        users = (await session.execute(query)).all()

    sent_count = 0

    for user in users:
        user_id = user.id
        user_group_id = user.group_id
        user_favorites = user.favorite_groups or []
        user_teacher_name = user.teacher_name

        user_changed_groups = []

        if user_group_id in changed_group_ids:
            user_changed_groups.append(groups_map[user_group_id])

        if user_teacher_name is not None:
            for fav_id in user_favorites:
                if fav_id in changed_group_ids and groups_map[fav_id] not in user_changed_groups:
                    user_changed_groups.append(groups_map[fav_id])

        if not user_changed_groups:
            continue

        if user_teacher_name is None:  # У студентов уведомление только у своей группы
            text = f"\U0001f514 <b>Расписание вашей группы обновлено</b>"
        else:
            if len(user_changed_groups) == 1:
                text = f"\U0001f514 Расписание избранной группы <b>{user_changed_groups[0]}</b> обновлено"
            else:
                groups_list = "\n".join(f"• {name}" for name in user_changed_groups)
                text = f"\U0001f514 Расписание избранных групп обновлено:\n{groups_list}"

        with suppress(TelegramBadRequest):
            await bot.send_message(user_id, text, reply_markup=KB.restart_to_schedule(), parse_mode="HTML")
            sent_count += 1
            await asyncio.sleep(0.2)

    await bot.send_message(chat_id=config.administration_chat_id,
                           text=f"\U0001f514 Уведомления о изменениях отправлено для {sent_count} чел.")


async def check_groups_changes_and_notify(bot) -> None:
    """
    Функция для APScheduler
    """
    current_groups = await fetch_groups_info()
    if not current_groups:
        return

    cached_data = load_cached_data()

    if cached_data is None:
        save_cached_data(current_groups)
        return

    changed_groups = get_changed_groups(current_groups, cached_data)

    if changed_groups:
        await send_schedule_update_notification(bot, changed_groups)

    save_cached_data(current_groups)
