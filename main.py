import asyncio
import locale
import logging
import sys
from datetime import datetime

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.callback_answer import CallbackAnswerMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config_reader import config, sessionmaker
from database.models import db_init
from handlers.errors import errors_handler_router
from handlers.managment.panel import admin_panel_router
from handlers.managment.statistics import statstics_router
from handlers.users.auth import auth_router
from handlers.users.favorite_groups import favorite_groups_router
from handlers.users.main_menu import main_menu_router
from handlers.users.teachers_viewer import teachers_router
from middlewares.db import DbSessionMiddleware
from middlewares.throttling import ThrottlingMiddleware
from modules.groups_cache import check_groups_changes_and_notify


async def main():
    await db_init()

    # fsm_storage = RedisStorage.from_url(str(config.redis_uri))
    fsm_storage = MemoryStorage()

    bot = Bot(config.bot_token.get_secret_value(), parse_mode="HTML")

    dp = Dispatcher(storage=fsm_storage)
    dp.update.middleware(DbSessionMiddleware(session_pool=sessionmaker))

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

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        check_groups_changes_and_notify,
        trigger="interval",
        minutes=30,
        next_run_time=datetime.now(),
        args=[bot],
        id="groups_update_check"
    )
    scheduler.start()

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
