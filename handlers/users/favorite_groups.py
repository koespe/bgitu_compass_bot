import aiohttp
from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InputMediaPhoto

import states
from config_reader import graphics_id, config
from database.base import DB
from handlers.users.main_menu import handle_schedule
from keyboards import KB

favorite_groups_router = Router()


# todo: не забыть про удлаение ("удалить группу")


@favorite_groups_router.callback_query(F.data.in_({'favorite_group_delete_button', 'favorite_groups'}))
async def favorite_groups_menu(callback: CallbackQuery, state: FSMContext):
    fsm_data = await state.get_data()
    try:
        await callback.bot.edit_message_media(
            chat_id=callback.from_user.id,
            message_id=fsm_data.get('photo_msg_id'),
            media=InputMediaPhoto(media=graphics_id['favorites_main_menu'])
        )
    except TelegramBadRequest:
        pass

    is_deleting = True if callback.data == 'favorite_group_delete_button' else False

    if is_deleting:
        msg_text = 'Нажмите на название группы чтобы удалить ее из списка'
    else:
        msg_text = 'Добавьте группы знакомых/друзей в избранные и быстро просматривайте их расписание!\n'
    await callback.message.edit_text(
        text=msg_text,
        reply_markup=await KB.favorites_main_menu(callback.from_user.id, is_deleting)
    )


@favorite_groups_router.callback_query(F.data == 'favorite_group_search')
async def favorite_group_search(callback: CallbackQuery, state: FSMContext):
    # Вызываем обычную функцию выбора группы, но прокидываем еще флаг
    fsm_data = await state.get_data()
    try:
        await callback.bot.edit_message_media(
            chat_id=callback.from_user.id,
            message_id=fsm_data.get('photo_msg_id'),
            media=InputMediaPhoto(media=graphics_id['favorites_search'])
        )
    except TelegramBadRequest:
        pass

    await state.update_data(favorites_request=True)
    await state.set_state(states.AuthState.requesting_group_name)
    await callback.message.edit_text(
        text='Введите поисковой запрос (можно ввести неполное название)\n'
             'Пример: "ПРИ" или "АД СПО"',
        reply_markup=KB.cancel_group_search()
    )
    await state.update_data(bot_msg_id=callback.message.message_id)


@favorite_groups_router.callback_query(F.data.startswith('favorite_group_open'))
async def handle_favorite_group_selection(callback: CallbackQuery, state: FSMContext):
    group_id = callback.data.split('=')[1]
    await state.update_data(favorite_group_id=group_id)
    async with aiohttp.ClientSession() as web_session:
        group_name_req = await web_session.get(url=config.api_host + f'groups?groupId={group_id}')
        group_name_resp: dict = await group_name_req.json()
        group_name = group_name_resp[0].get('name')
    await state.update_data(favorite_group_name=group_name)

    await handle_schedule(callback, state)


@favorite_groups_router.callback_query(F.data == 'favorite_group_exit')
async def handle_favorite_group_exit(callback: CallbackQuery, state: FSMContext):
    await state.update_data(favorite_group_id=None)
    await state.update_data(favorite_group_name=None)

    await handle_schedule(callback, state)


@favorite_groups_router.callback_query(F.data.startswith('favorite_group_delete'))
async def handle_favorite_group_delete_button(callback: CallbackQuery, state: FSMContext):
    group_id = callback.data.split('=')[1]
    await DB.manage_favorites(action='delete', user_id=callback.from_user.id, group_id=int(group_id))

    await favorite_groups_menu(callback, state)
