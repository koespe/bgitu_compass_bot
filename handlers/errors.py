import asyncio

from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import ExceptionTypeFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Update, ErrorEvent, Message

from database.base import DB
from handlers.users.auth import handle_start_command
from keyboards import KB
from modules.schudule_parser import form_schedule_message

errors_handler_router = Router()


@errors_handler_router.message(F.text == '/reset')
async def handle_logout(message: Message, state: FSMContext):
    await DB.logout(message.from_user.id)
    await state.clear()
    await message.answer('Ваши данные удалены из бота')
    await asyncio.sleep(1)
    await handle_start_command(message, state)


@errors_handler_router.error(ExceptionTypeFilter(TelegramBadRequest))
async def handle_my_custom_exception(event: ErrorEvent):
    try:  # Не уверен, что через isinstance(event.update.callback_query, CallbackQuery)
        user_id = event.update.callback_query.from_user.id
        await event.update.callback_query.answer(text='\U0001f50d Используйте новое сообщение')
        await event.update.callback_query.bot.send_message(chat_id=user_id,
                                                           text='Сообщение устарело\n'
                                                                '——> /start <——\n'
                                                                'Нажмите ^^^^^ выше')
    except:
        pass

# @errors_handler_router.error()  # handle the cases when this exception raises
# async def errors_handler(update: Update, exception):
#
#     if isinstance(exception, TelegramBadRequest):
#         user_id = update.from_user.id
#         await update.bot.send_message(chat_id=user_id,
#                                       text=await form_schedule_message(user_id=user_id, offset=0),
#                                       reply_markup=await KB.schedule(user_id=user_id, offset=0))
#         return True  # errors_handler must return True if error was handled correctly
