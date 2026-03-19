import asyncio
import locale
import logging
import sys
from datetime import datetime

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.callback_answer import CallbackAnswerMiddleware
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config_reader import config, sessionmaker, graphics
from database.models import db_init
from handlers.errors import errors_handler_router
from handlers.managment.panel import admin_panel_router
from handlers.managment.statistics import statstics_router
from handlers.users.auth import auth_router
from handlers.users.favorite_groups import favorite_groups_router
from handlers.users.main_menu import main_menu_router
from handlers.users.teachers_viewer import teachers_router
from middlewares.db import DbSessionMiddleware
from middlewares.lockdown import LockdownMiddleware
from middlewares.throttling import ThrottlingMiddleware
from modules.annual_reset import enable_bot_lockdown, check_new_groups_and_disable_lockdown
from modules.groups_cache import check_groups_changes_and_notify


async def main():
    await db_init()

    bot = Bot(config.bot_token.get_secret_value(), parse_mode="HTML")
    await graphics.validate(bot)

    # fsm_storage = RedisStorage.from_url(str(config.redis_uri))
    fsm_storage = MemoryStorage()
    dp = Dispatcher(storage=fsm_storage)

    dp.update.middleware(DbSessionMiddleware(session_pool=sessionmaker))
    dp.message.middleware(LockdownMiddleware())
    dp.callback_query.middleware(LockdownMiddleware())
    dp.callback_query.middleware(CallbackAnswerMiddleware())  # Auto reply to all callbacks
    dp.message.middleware(ThrottlingMiddleware())
    # dp.callback_query.middleware(ThrottlingMiddleware())

    dp.include_router(errors_handler_router)
    dp.include_router(auth_router)
    dp.include_router(teachers_router)
    dp.include_router(main_menu_router)
    dp.include_router(favorite_groups_router)
    dp.include_router(statstics_router)
    dp.include_router(admin_panel_router)

    logging.basicConfig(
        level=logging.INFO,
        # filename='logs/logs.log',
        # filemode='a',
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
    )

    platform_name = sys.platform
    if platform_name.startswith('win'):
        locale.setlocale(locale.LC_TIME, 'Russian_Russia.1251')
    else:
        locale.setlocale(locale.LC_TIME, 'ru_RU.utf8')

    # jobstores = {'default': RedisJobStore(db=1)}
    jobstores = {'default': MemoryJobStore()}
    scheduler = AsyncIOScheduler(jobstores=jobstores)
    scheduler.add_job(
        check_groups_changes_and_notify,
        trigger="interval",
        minutes=30,
        next_run_time=datetime.now(),
        args=[bot],
        id="groups_update_check"
    )
    scheduler.add_job(
        enable_bot_lockdown,
        trigger="cron",
        month=7,
        day=15,
        hour=0,
        minute=0,
        id="annual_lockdown",
        misfire_grace_time=604800)  # 7 дней
    scheduler.add_job(
        check_new_groups_and_disable_lockdown,
        trigger="interval",
        minutes=30,
        next_run_time=datetime.now(),
        args=[bot],
        id="lockdown_check",
    )
    scheduler.start()

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
