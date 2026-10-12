import asyncio
import locale
import logging
import sys
from datetime import datetime

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage
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
from modules.annual_reset import ensure_annual_lockdown
from modules.api_client import close_session
from modules.groups_cache import check_groups_changes_and_notify
from modules.site_updates import check_site_updates_and_notify

PROJECT_LOGGERS = (
    "main",
    "__main__",
    "config_reader",
    "handlers",
    "middlewares",
    "modules",
    "database",
    "keyboards",
    "states",
)


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.ERROR,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )
    for logger_name in PROJECT_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.DEBUG)


async def main():
    setup_logging()
    await db_init()

    bot = Bot(config.bot_token.get_secret_value(), parse_mode="HTML")
    await graphics.validate(bot)

    platform_name = sys.platform
    if platform_name.startswith('win'):
        locale.setlocale(locale.LC_TIME, 'Russian_Russia.1251')
        fsm_storage = MemoryStorage()
    else:
        locale.setlocale(locale.LC_TIME, 'ru_RU.utf8')
        fsm_storage = RedisStorage.from_url(str(config.redis_uri))

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
        check_site_updates_and_notify,
        trigger="interval",
        minutes=30,
        next_run_time=datetime.now(),
        args=[bot],
        id="site_updates_check"
    )
    scheduler.add_job(
        ensure_annual_lockdown,
        trigger="interval",
        minutes=60,
        next_run_time=datetime.now(),
        id="annual_lockdown_check"
    )
    scheduler.start()

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown()
        await close_session()


if __name__ == "__main__":
    asyncio.run(main())
