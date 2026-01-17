import asyncio
import locale
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.utils.callback_answer import CallbackAnswerMiddleware

from config_reader import config, sessionmaker
from database.models import db_init
from handlers.managment.statistics import statstics_router
from handlers.errors import errors_handler_router
from handlers.managment.panel import admin_panel_router
from handlers.users.auth import auth_router
from handlers.users.favorite_groups import favorite_groups_router
from handlers.users.main_menu import main_menu_router
from handlers.users.teachers_viewer import teachers_router

from middlewares.db import DbSessionMiddleware
from middlewares.throttling import ThrottlingMiddleware


async def main():
    await db_init()

    # fsm_storage = RedisStorage.from_url(str(config.redis_uri))
    fsm_storage = MemoryStorage()

    bot = Bot(config.bot_token.get_secret_value(), parse_mode="HTML")

    # Setup dispatcher and bind routers to it
    dp = Dispatcher(storage=fsm_storage)
    dp.update.middleware(DbSessionMiddleware(session_pool=sessionmaker))

    # Automatically reply to all callbacks
    dp.callback_query.middleware(CallbackAnswerMiddleware())
    dp.message.middleware(ThrottlingMiddleware())
    # dp.callback_query.middleware(ThrottlingMiddleware())

    # Register handlers
    dp.include_router(errors_handler_router)
    dp.include_router(auth_router)
    dp.include_router(teachers_router)
    dp.include_router(main_menu_router)
    dp.include_router(favorite_groups_router)
    dp.include_router(statstics_router)
    dp.include_router(admin_panel_router)

    # Setup logging
    # logging.basicConfig(
    #     level=logging.WARNING,
    #     filename='logs/logs.log',
    #     filemode='a',
    #     format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
    # )

    platform_name = sys.platform
    if platform_name.startswith('win'):
        locale.setlocale(locale.LC_TIME, 'Russian_Russia.1251')
    else:
        locale.setlocale(locale.LC_TIME, 'ru_RU.utf8')

    # Run bot
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
