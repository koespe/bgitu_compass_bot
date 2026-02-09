import asyncio
import re
from contextlib import suppress
from functools import wraps

from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select, func

from config_reader import config
from database.base import get_session
from database.models import Users
from keyboards import KB
from states import Broadcast, AdMessage

admin_panel_router = Router()


def IsAdmin():
    def decorator(func):
        @wraps(func)
        async def wrapper(message: Message):
            return message.from_user.id == config.admin_tg_id

        return wrapper

    return decorator


@admin_panel_router.message(IsAdmin(), F.photo)
async def send_photo_data(message: Message):
    """
    Сохранение id фото для использования в graphics
    """
    await message.reply(message.photo[-1].file_id)


@admin_panel_router.message(IsAdmin(), F.text == '/admin')
async def admin_panel(message: Message):
    async with get_session() as session:
        query = select(func.count(Users.id))
        users_count = (await session.execute(query)).scalar()
        stats_message = 'Статистика:\n' f'Всего: {users_count} пользователей\n'

        query = select(Users.group_name, func.count(Users.group_name)).group_by(Users.group_name)
        result = (await session.execute(query)).all()
        for group_name, count in sorted(result, key=lambda x: x[1], reverse=True):
            stats_message += f'{group_name}: {count}\n'

    if config.admin_tg_id == message.from_user.id:
        await message.answer(text=stats_message, reply_markup=KB.admin_panel())


@admin_panel_router.callback_query(F.data == 'broadcast')
async def broadcast_select_type(callback: CallbackQuery):
    await callback.message.answer(text='Выбери тип рассылки', reply_markup=KB.broadcast_types())


@admin_panel_router.callback_query(F.data == 'broadcast_type=id_list')
async def broadcast_waiting_id_list(callback: CallbackQuery, state: FSMContext):
    await state.update_data(broadcast_type='id_list')
    await callback.message.answer(text='Ожидаю список где каждый id с новой строки')
    await state.set_state(Broadcast.requesting_list_id)


@admin_panel_router.message(StateFilter(Broadcast.requesting_list_id))
async def broadcast_fetching_id_list(message: Message, state: FSMContext):
    id_list = list(map(int, message.text.split('\n')))
    await state.update_data(id_list=id_list)
    await message.answer(text='Выбери клавиатуру', reply_markup=KB.broadcast_keyboards())


@admin_panel_router.callback_query(F.data == 'broadcast_type=all')
async def broadcast_select_keyboard(callback: CallbackQuery):
    await callback.message.answer(text='Выбери клавиатуру', reply_markup=KB.broadcast_keyboards())


@admin_panel_router.callback_query(F.data.startswith('broadcast_kb_'))
async def broadcast_request(callback: CallbackQuery, state: FSMContext):
    if 'update' in callback.data:
        await state.update_data(restart_kb=True)

    await state.set_state(Broadcast.requesting_message)
    await callback.message.answer(text='Введи текст рассылки', reply_markup=KB.cancel_broadcast())


@admin_panel_router.message(StateFilter(Broadcast.requesting_message))
async def handle_start_broadcast(message: Message, state: FSMContext):
    broadcast_text = message.text

    fsm_data = await state.get_data()
    is_restart_kb = True if fsm_data.get('restart_kb') else False
    id_list = fsm_data.get('id_list')

    async with get_session() as session:
        query = select(Users.id)
        users = (await session.execute(query)).fetchall()
        user_list = list(user[0] for user in users)
    iteration_list = id_list if id_list is not None else user_list

    kwargs = {"reply_markup": KB.restart_to_schedule(), "disable_notification": True} if is_restart_kb else {}

    for user in iteration_list:
        with suppress(Exception):
            await message.bot.send_message(user, broadcast_text, parse_mode='html', **kwargs)
        await asyncio.sleep(0.2)

    await state.clear()
    await message.answer(text='Рассылка закончена.')


@admin_panel_router.callback_query(F.data == 'cancel_broadcast')
async def handle_cancel_broadcast(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer(text='Отменено.')


@admin_panel_router.message(F.text == '/ad')
async def get_message_id(message: Message, state: FSMContext):
    """
    Запрос сообщения для рекламной рассылки с возможностью использования Premium-эмодзи
    """
    await state.set_state(AdMessage.requesting_message)
    await message.answer(text='Пришлите любое сообщение')


@admin_panel_router.message(StateFilter(AdMessage.requesting_message))
async def handle_send_ad_message(message: Message, state: FSMContext):
    await message.answer(f'from_chat_id={message.chat.id}, message_id={message.message_id}')
    await message.answer('Перешлите сообщение выше администратору')
    await state.clear()


@admin_panel_router.callback_query(F.data == 'broadcast_type=ad')
async def ad_waiting_data(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Broadcast.requesting_ad_data)
    await callback.message.answer(
        text='Ожидаю сообщение от бота вида\n from_chat_id={message.chat.id}, message_id={message.message_id}'
    )


@admin_panel_router.message(StateFilter(Broadcast.requesting_ad_data))
async def broadcast_ad(message: Message, state: FSMContext):
    input_string = message.text
    from_chat_id_match = re.search(r"from_chat_id=(-?\d+)", input_string)
    message_id_match = re.search(r"message_id=(\d+)", input_string)

    from_chat_id = None
    message_id = None

    if from_chat_id_match:
        from_chat_id = int(from_chat_id_match.group(1))

    if message_id_match:
        message_id = int(message_id_match.group(1))

    if not from_chat_id or not message_id:
        await state.clear()
        await message.answer(text='Не удалось найти необходимые аргументы (from_chat_id и message_id).')
        return

    async with get_session() as session:
        query = select(Users.id)
        users = (await session.execute(query)).fetchall()
        user_list = list(user[0] for user in users)

    for user in user_list:
        try:
            await message.bot.forward_message(
                chat_id=user, from_chat_id=from_chat_id, message_id=message_id, disable_notification=True
            )
        except:
            continue
        await asyncio.sleep(0.2)

    await state.clear()
    await message.answer(text='Рассылка закончена.')
