import asyncio
import json
import logging
from contextlib import suppress
from datetime import date
from pathlib import Path
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import select

from config_reader import config
from database.base import get_session
from database.models import Users
from keyboards import KB
from middlewares.lockdown import is_lockdown_active, lockdown_cache, read_lockdown_state, write_lockdown_state
from modules.api_client import get_groups, invalidate_lessons

CACHE_FILE = Path("data") / "groups_cache.json"
logger = logging.getLogger(__name__)


def load_cached_data() -> Optional[dict[str, dict]]:
    if not CACHE_FILE.exists():
        return None

    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        logger.exception(f"Не удалось прочитать кэш групп из {CACHE_FILE.resolve()}")
        return None


def save_cached_data(groups: list[dict]) -> None:
    cache_data = {str(group["id"]): group for group in groups}

    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
    except Exception:
        logger.exception(f"Не удалось сохранить кэш групп в {CACHE_FILE.resolve()}")


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


def get_removed_group_ids(current_groups: list[dict], cached_data: Optional[dict[str, dict]]) -> set[int]:
    if cached_data is None:
        return set()

    current_ids = {group['id'] for group in current_groups}

    removed = set()
    for group_id in cached_data:
        try:
            parsed_id = int(group_id)
        except (TypeError, ValueError):
            continue
        if parsed_id not in current_ids:
            removed.add(parsed_id)

    return removed


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


async def handle_new_groups(bot: Bot, new_groups: list[dict]) -> None:
    async with get_session() as session:
        query = select(Users.id).where(
            (Users.group_id.is_(None)) & (Users.teacher_name.is_(None))
        )
        users = (await session.execute(query)).all()

    groups_list = "\n".join(f"• {g.get('name', g['id'])}" for g in new_groups)
    text = f"🎉 <b>Появились новые группы!</b>\n\n{groups_list}"

    for user in users:
        with suppress(TelegramBadRequest):
            await bot.send_message(user.id, text, reply_markup=KB.start_menu())

    await bot.send_message(
        chat_id=config.administration_chat_id,
        text=f"🔔 <b>Обнаружены новые группы</b>\nПоявилось групп: {len(new_groups)}\n\n{text}"
    )

    state = read_lockdown_state()
    state["active"] = False
    write_lockdown_state(state)
    lockdown_cache.clear()


async def check_groups_changes_and_notify(bot: Bot) -> None:
    """
    send_schedule_update_notification пользователям, у кого выбрана группа,
    а handle_new_groups — тем, у кого группа не выбрана

    in_lockdown_window нужно чтобы корректно обработать момент удаления данных на API
    (возможно удаление произойдет не 15 июля, в таком случае lockdown будет установлен 100% корректно)
    """
    today = date.today()
    in_lockdown_window = date(today.year, 8, 1) <= today <= date(today.year, 10, 1)

    if is_lockdown_active() and not in_lockdown_window:
        return

    current_groups = await get_groups()
    if not current_groups:  # API недоступен или нет групп
        return

    cached_data = load_cached_data()

    changed_groups = get_changed_groups(current_groups, cached_data)
    removed_group_ids = get_removed_group_ids(current_groups, cached_data)

    # Когда на сайте изменяется расписание, то удаляем только изменившиеся и исчезнувшие группы
    ids_to_delete = [group['id'] for group in changed_groups] + sorted(removed_group_ids)
    purged = invalidate_lessons(ids_to_delete)
    if purged:
        logger.info("Снесён кеш расписания: %d из %d групп, затронуты %s",
                    purged, len(ids_to_delete), ids_to_delete)

    try:
        if changed_groups:
            await send_schedule_update_notification(bot, changed_groups)

        if in_lockdown_window:
            if cached_data is None:
                added_groups = current_groups
            else:
                cached_ids = set(cached_data.keys())
                added_groups = [g for g in current_groups if str(g['id']) not in cached_ids]

            if added_groups:
                await handle_new_groups(bot, added_groups)
    finally:
        save_cached_data(current_groups)
