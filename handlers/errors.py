from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import ExceptionTypeFilter
from aiogram.types import ErrorEvent

errors_handler_router = Router()


@errors_handler_router.error(ExceptionTypeFilter(TelegramBadRequest))
async def handle_my_custom_exception(event: ErrorEvent):
    try:
        user_id = event.update.callback_query.from_user.id
        await event.update.callback_query.answer(text='\U0001f50d Используйте новое сообщение')
        await event.update.callback_query.bot.send_message(chat_id=user_id,
                                                           text='Сообщение устарело\n'
                                                                '——> /start <——\n'
                                                                'Нажмите ^^^^^ выше')
    except:
        pass
