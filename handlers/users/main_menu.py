import asyncio
import datetime
from typing import Union

import aiohttp
from aiogram import Router, F, Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, Update, InputMediaPhoto
from aiogram.filters import StateFilter

from config_reader import graphics_id
from database.base import DB
from keyboards import KB
from modules.schudule_parser import form_schedule_message

main_menu_router = Router()


# Сюда приходят с Callback и Message
@main_menu_router.callback_query(F.data == 'back_to_schedule')
async def handle_schedule(update: Union[Update, CallbackQuery, Message], state: FSMContext):
    await state.set_state(state=None)  # Это может быть возврат из пунктов меню с ожиданием user input
    user_id = update.from_user.id

    fsm_data = await state.get_data()
    offset = fsm_data.get('offset')
    last_action = fsm_data.get('action')

    # мы должны знать schedule_view потому что при daily и weekly разная логика
    user_data = await DB.user_data(user_id)
    schedule_view = user_data.get('last_schedule_view')

    last_use_date = fsm_data.get('last_use_date')
    if last_use_date is None or fsm_data.get('refresh'):  # Если человек сделал /start или нажал refresh
        last_use_date = datetime.datetime.today().strftime('%Y-%m-%d')
    if offset is None:
        if schedule_view == 'daily' and datetime.datetime.now().hour > 15: # Вряд ли нужно расписание на сегодня
            offset = 1
        elif schedule_view == 'weekly' and datetime.datetime.now().weekday() == 6:
            offset = 1
        else:
            offset = 0
        await state.update_data(offset=offset)
    else:  # Offset мог устареть
        last_use_date_obj = datetime.datetime.strptime(last_use_date, '%Y-%m-%d')
        if schedule_view == 'daily':
            if datetime.date.today() != last_use_date_obj:
                calc_offset = datetime.date.today().day - last_use_date_obj.day
                offset -= calc_offset
                await state.update_data(offset=offset)
        elif schedule_view == 'weekly':
            if datetime.date.today().isocalendar().week != last_use_date_obj.isocalendar().week:
                offset -= datetime.date.today().isocalendar().week - last_use_date_obj.isocalendar().week
                await state.update_data(offset=offset)

    favorite_group_id = fsm_data.get('favorite_group_id')
    favorite_group_name = fsm_data.get('favorite_group_name')
    is_favorite = True if favorite_group_id else False
    graphics = graphics_id['favorites_schedule'] if is_favorite else graphics_id['schedule']

    is_holiday_skipped = False
    for _ in range(offset, offset + 7):
        msg_text = await form_schedule_message(user_id=user_id, offset=offset,
                                               favorite_group_id=favorite_group_id,
                                               favorite_group_name=favorite_group_name)
        
        # Проверяем на ошибку группы не найдена
        if msg_text == "GROUP_NOT_FOUND_ERROR":
            # Отправляем пользователя в главное меню для выбора новой группы
            from handlers.users.auth import handle_start_command
            await handle_start_command(update, state)
            return
        
        # Проверяем на ошибку с избранной группой
        if msg_text.startswith("❌ Группа") and "не найдена в расписании" in msg_text:
            # Показываем сообщение об ошибке и возвращаем в меню избранных групп
            if isinstance(update, CallbackQuery):
                await update.answer(text=msg_text)
            else:
                await update.bot.send_message(chat_id=user_id, text=msg_text)
            
            # Возвращаем в меню избранных групп
            from handlers.users.favorite_groups import favorite_groups_menu
            await favorite_groups_menu(update, state)
            return
        
        if len(msg_text) == 0:
            if last_action == 'next' or last_action is None:  # Может выходной сегодня
                offset += 1
            elif last_action == 'prev':
                offset -= 1
            is_holiday_skipped = True
        else:
            await state.update_data(offset=offset)
            break  # Получили расписание, идем дальше
    if is_holiday_skipped and isinstance(update, CallbackQuery):
        await update.answer(text='Выходной пропущен')

    kb = await KB.schedule(user_id, offset, is_favorite)

    if isinstance(update, Message) or (isinstance(update, CallbackQuery) and fsm_data.get('refresh')):
        photo_msg = await update.bot.send_photo(
            chat_id=user_id,
            photo=graphics
        )
        await update.bot.send_message(
            chat_id=user_id,
            text=msg_text,
            reply_markup=kb
        )
        await state.update_data(photo_msg_id=photo_msg.message_id)
    else:  # Стандартная ситуация
        try:
            await update.bot.edit_message_media(
                chat_id=user_id,
                message_id=fsm_data.get('photo_msg_id'),
                media=InputMediaPhoto(media=graphics)
            )
        except TelegramBadRequest:
            pass

        await update.bot.edit_message_text(
            chat_id=user_id,
            message_id=update.message.message_id,
            text=msg_text,
            reply_markup=kb
        )
    # Так как сообщение уже было обновлено, то обновляем last_day_accessed
    await state.update_data(last_use_date=datetime.datetime.today().strftime('%Y-%m-%d'))
    await state.update_data(refresh=None)


@main_menu_router.callback_query(F.data.startswith('schedule_page'))
async def handle_page_changes(update: Update, state: FSMContext):
    user_data = await state.get_data()
    offset = user_data.get('offset')

    action = update.data[14:]
    if action == "prev":
        offset -= 1
        await state.update_data(offset=offset)
    elif action == "next":
        offset += 1
        await state.update_data(offset=offset)
    elif action == 'refresh':
        action = 'next'
        await state.update_data(refresh=True)
        await state.update_data(offset=0)
        try:
            await update.bot.delete_message(
                chat_id=update.from_user.id,  # БЕЗ .message
                message_id=user_data.get('photo_msg_id')
            )
            await update.message.delete()
        except:
            pass

    await state.update_data(action=action)
    await handle_schedule(update, state)


@main_menu_router.callback_query(F.data == 'settings_main')
async def settings(update: Update, state: FSMContext):
    user_id = update.from_user.id
    fsm_data = await state.get_data()
    user_data = await DB.user_data(user_id)
    group_name = user_data.get('group_name')
    graphics = InputMediaPhoto(media=graphics_id['settings'])
    await update.bot.edit_message_media(
        chat_id=user_id,
        message_id=fsm_data.get('photo_msg_id'),
        media=graphics
    )
    await update.message.edit_text(text=f'Ваша группа: <b>{group_name}</b>',
                                   reply_markup=KB.settings())


@main_menu_router.callback_query(F.data == 'schedule_change_view')
async def handle_change_schedule_view(update: Update, state: FSMContext):
    user_id = update.from_user.id
    await DB.change_schedule_view(user_id)
    await state.update_data(offset=0)
    await handle_schedule(update, state)
