import os
from datetime import date
from pathlib import Path

from sqlalchemy import update

from database.models import Users, engine
from middlewares.lockdown import lockdown_cache, read_lockdown_state, write_lockdown_state

GROUPS_CACHE_FILE = Path("data") / "groups_cache.json"


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

    state = read_lockdown_state()
    state["active"] = True
    state["applied_date"] = date.today().isoformat()
    write_lockdown_state(state)

    lockdown_cache.clear()

    if GROUPS_CACHE_FILE.exists():
        os.remove(GROUPS_CACHE_FILE)


async def ensure_annual_lockdown() -> None:
    """
     С 15 июля по 14 августа включительно, включаем lockdown режим, если в этом году он ещё не включался.
    """
    today = date.today()
    if not (date(today.year, 7, 15) <= today < date(today.year, 8, 15)):
        return

    applied_date = read_lockdown_state().get("applied_date")
    if applied_date:
        try:
            if date.fromisoformat(applied_date).year == today.year:
                return
        except ValueError:
            pass

    await enable_bot_lockdown()
