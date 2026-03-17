import json
import os
from contextlib import suppress
from datetime import date
from pathlib import Path

import aiohttp
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import select
from sqlalchemy import update

from config_reader import config
from database.base import get_session
from database.models import Users, engine
from middlewares.lockdown import lockdown_cache, is_lockdown_active

LOCKDOWN_FILE = Path("data") / "lockdown.json"
GROUPS_SNAPSHOT_FILE = Path("data") / "groups_snapshot.json"
GROUPS_CACHE_FILE = Path("data") / "groups_cache.json"
GROUPS_SNAPSHOT_OLD_FILE = Path("data") / "groups_snapshot_old.json"


async def enable_bot_lockdown():
    async with engine.begin() as conn:
        await conn.execute(
            update(Users).values(
                group_name=None,
                group_id=None,
                last_schedule_view='weekly',
                teacher_name=None,
                favorite_groups=[]
            )
        )

    with open(LOCKDOWN_FILE, "w", encoding="utf-8") as f:
        json.dump({"active": True}, f, ensure_ascii=False)

    lockdown_cache.clear()

    for file_path in [GROUPS_CACHE_FILE, GROUPS_SNAPSHOT_OLD_FILE]:
        if file_path.exists():
            os.remove(file_path)


async def check_new_groups_and_disable_lockdown(bot: Bot) -> None:
    """
    `return` == "доступ пока не открываем"
    """
    # После 15 октября не уведомляем о новых группах (МАГ появляется позже)
    if date.today() > date(date.today().year, 10, 15):
        return

    async with aiohttp.ClientSession() as session:
        response = await session.get(config.api_host + "groups")
        if response.status != 200:
            return
        groups = await response.json()
        if not groups:
            return

        new_groups = []

        if GROUPS_SNAPSHOT_OLD_FILE.exists():
            with open(GROUPS_SNAPSHOT_OLD_FILE, "r", encoding="utf-8") as f:
                old_groups = json.load(f)
            old_ids = {g["id"] for g in old_groups}
            new_groups = [g for g in groups if g["id"] not in old_ids]

        if new_groups:
            with open(GROUPS_SNAPSHOT_FILE, "w", encoding="utf-8") as f:
                json.dump(groups, f, ensure_ascii=False, indent=2)

            if is_lockdown_active():
                with open(LOCKDOWN_FILE, "w", encoding="utf-8") as f:
                    json.dump({"active": False}, f, ensure_ascii=False)
                lockdown_cache.clear()

            async with get_session() as session:
                query = select(Users.id).where(
                    (Users.group_id.is_(None)) & (Users.teacher_name.is_(None))
                )
                users = (await session.execute(query)).all()

            groups_list = "\n".join(f"• {g.get('name', g['id'])}" for g in new_groups)
            text = f"\U0001F389 <b>Появились новые группы!</b>\n\n{groups_list}"

            for user in users:
                with suppress(TelegramBadRequest):
                    await bot.send_message(user.id, text, parse_mode="HTML")

            await bot.send_message(
                chat_id=config.administration_chat_id,
                text=f"\U0001F514 <b>Обнаружены новые группы</b>\nПоявилось групп: {len(new_groups)}\n\n{text}",
                parse_mode="HTML"
            )

        with open(GROUPS_SNAPSHOT_OLD_FILE, "w", encoding="utf-8") as f:
            json.dump(groups, f, ensure_ascii=False, indent=2)
