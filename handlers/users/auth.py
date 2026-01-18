import asyncio
import re
from typing import Union

import aiohttp
from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, Update, InputMediaPhoto
from aiogram.filters import CommandStart, StateFilter

from config_reader import config, graphics_id
from database.base import DB
from handlers.users.favorite_groups import favorite_groups_menu
from handlers.users.main_menu import handle_schedule
from keyboards import KB
from states import AuthState

auth_router = Router()


class SupportWordsState(StatesGroup):
    waiting_for_msg = State()


@auth_router.message(CommandStart(deep_link=True, magic=F.args == "support_words"))
async def handle_support_words(message: Message, state: FSMContext):
    msg_text = ('\U0001f917 Вы можете поддержать разработчиков теплыми словами, нам будет очень приятно!\n'
            'Напишите одно сообщение')
    await message.answer(msg_text)
    await state.set_state(SupportWordsState.waiting_for_msg)


@auth_router.message(StateFilter(SupportWordsState.waiting_for_msg))
async def send_support_words(message: Message, state: FSMContext):
    # Переслать сообщение со всеми вложениями
    await message.answer('Спасибо за поддержку!')
    await message.forward(chat_id=198685526)
    await state.set_state(state=None)


@auth_router.message(CommandStart())
async def handle_start_command(update: Union[Message, CallbackQuery, Update], state: FSMContext):
    await state.clear()

    if await DB.is_user_authorized(update.from_user.id):
        await handle_schedule(update, state)
    else:
        if isinstance(update, Message):
            photo_msg = await update.answer_photo(
                photo=graphics_id['start_menu']
            )
            await state.update_data(photo_msg_id=photo_msg.message_id)
            await update.answer(
                text='Этот бот поможет узнать <b>расписание групп бакалавриата, СПО и магистратуры</b>\n\n'
                     '\u26a1 Удобное <b>приложение для Android</b> → bgitu-compass.ru',
                reply_markup=KB.start_menu()
            )
        else:
            fsm_data = await state.get_data()
            try:
                await update.bot.edit_message_media(
                    chat_id=update.from_user.id,
                    message_id=fsm_data.get('photo_msg_id'),
                    media=InputMediaPhoto(media=graphics_id['start_menu'])
                )
            except TelegramBadRequest:
                pass
            await update.message.edit_text(
                text='Этот бот поможет узнать <b>расписание групп бакалавриата, СПО и магистратуры</b>\n\n'
                     '\u26a1 Удобное <b>приложение для Android</b> → bgitu-compass.ru',
                reply_markup=KB.start_menu())


@auth_router.callback_query(F.data == 'about')
async def about_project(callback: CallbackQuery):
    about_text = (
        'Этот <b>неофициальный</b> бот использует файлы расписания с сайта bgitu.ru — предоставляется расписание для групп <b><u>БАК, СПО и МАГ</u></b>\n'
        '\U0001f4f1 Также есть <b>приложение для Android</b> → bgitu-compass.ru\n\n'
        '\U0001f464 <b>Разработчик:</b> студент ПрИ-301 — <b>Пудов Кирилл (@koespe)</b>\n'
        '\U0001f464 <b>Разработчик приложения:</b> студент ПрИ-301 — <b>Елисей Веревкин (@Injent)</b>\n')
    await callback.message.edit_text(text=about_text,
                                     reply_markup=KB.start_menu(is_about=True))


@auth_router.callback_query(F.data == 'choose_group')
async def request_group_name(callback: CallbackQuery, state: FSMContext):
    fsm_data = await state.get_data()
    if fsm_data.get('offset') is not None:
        await state.update_data(old_user=True)  # флаг, чтобы не присылать уведомление "новый пользователь"
        # if fsm_data.get('favorites_request') is None:
        #     await DB.logout(callback.from_user.id)
    await state.set_state(AuthState.requesting_group_name)
    try:
        await callback.bot.edit_message_media(
            chat_id=callback.from_user.id,
            message_id=fsm_data.get('photo_msg_id'),
            media=InputMediaPhoto(media=graphics_id['group_search'])
        )
    except TelegramBadRequest:
        pass
    bot_msg = await callback.message.edit_text(
        text='\U0001f447 Введите группу (можно неполностью)\n'
             'Пример: «ИСТ», «АД СПО» или «ЭКОНм»',
        reply_markup=KB.cancel_group_search()
    )
    await state.update_data(bot_msg_id=bot_msg.message_id)


@auth_router.message(StateFilter(AuthState.requesting_group_name))
async def return_search_results(message: Message, state: FSMContext):
    search_query = message.text
    modified_query = search_query_text_process(search_query)

    fsm_data = await state.get_data()
    bot_msg_id = fsm_data.get('bot_msg_id')

    await message.delete()  # Поисковой запрос пользователя

    async with aiohttp.ClientSession() as web_session:
        search_req = await web_session.get(url=config.api_host + f'groups?searchQuery={modified_query}')
        search_resp = await search_req.json()  # [{"id": 114, "name": "ПРИ-101"}, ...]

    if len(search_resp) == 0:
        await message.bot.edit_message_text(
            chat_id=message.from_user.id,
            message_id=bot_msg_id,
            text=f'\U0001f914 По запросу "{search_query}" ничего не нашлось.\n\n'
                 'Бот отображает <b>только группы бакалавриата, магистратуры и СПО</b>\n\n'
                 'Если вы <b>БАК или СПО</b> — проверьте написание группы (для СПО необходимо писать "АД СПО" <u>или просто "СПО"</u>).\n\n'
                 '\U0001f447 Введите новый запрос ниже'
        )
    else:
        await message.bot.edit_message_text(
            chat_id=message.from_user.id,
            message_id=bot_msg_id,
            text='Выберите группу \U0001f447',
            reply_markup=KB.groups_search_results(search_resp)
        )


@auth_router.callback_query(F.data.startswith('select_group'))
async def bind_group_to_user(callback: CallbackQuery, state: FSMContext):
    fsm_data = await state.get_data()
    raw_group_data = callback.data.split('_')
    group_id = int(raw_group_data[2])
    group_name = raw_group_data[3]

    if fsm_data.get('favorites_request') is not None:
        # Добавляем в бд в избранные
        await DB.manage_favorites(action='add', user_id=callback.from_user.id, group_id=group_id)
        await state.set_state(state=None)
        await state.update_data(favorites_request=None)
        await favorite_groups_menu(callback, state)
    else:
        if fsm_data.get('old_user'):
            await DB.logout(callback.from_user.id)
        await DB.add_user(user_id=callback.from_user.id, group_name=group_name, group_id=group_id)
        if re.search(r'[А-Яа-я]м', group_name):  # Обработка если это магистратура
            await DB.change_schedule_view(user_id=callback.from_user.id)
        await callback.bot.delete_message(
            chat_id=callback.from_user.id,
            message_id=fsm_data.get('photo_msg_id')
        )
        await callback.message.delete()
        await callback.message.answer(f'Вы выбрали группу {group_name}')
        await asyncio.sleep(1)

        if not fsm_data.get('old_user'):
            await callback.message.answer(
                '\u270d\ufe0f <b>Быстрый экскурс в бота</b>\n\n'
                '\U0001f4d6 — <b>лекция</b>\n'
                '\U0001f52c — <b>практика</b>\n'
                '\U0001f464 Расписание преподавателей — узнайте в 2 клика, где можно найти преподавателя\n\n'
                '\U0001f5e8\ufe0f Если есть предложения/замечания — пишите мне! @koespe'
            )
            await asyncio.sleep(3)
            # await callback.bot.send_message(
            #     chat_id=config.admin_tg_id,
            #     text=f'Новый пользователь: {group_name}, @{callback.from_user.username}'
            # )

        await state.clear()
        await state.update_data(refresh=True)  # Чтобы приходя с Callback отравилось новое сообщение
        await handle_schedule(callback, state)


# Help page
@auth_router.callback_query(F.data == 'no_mine_group')
async def no_group_info(callback: CallbackQuery, state: FSMContext):
    help_text = ('Бот отображает <b>только группы бакалавриата, магистратуры и СПО</b>\n\n'
                 'Если вы обучаетесь <b>на магистратуре</b> — введите "маг"\n'
                 'Если вы <b>БАК или СПО</b> — проверьте написание группы (для СПО необходимо писать "АД СПО" <u>или просто "СПО"</u>).\n\n'
                 '\U0001f447 Введите новый запрос ниже')
    bot_msg_id = (await state.get_data()).get('bot_msg_id')
    await callback.bot.edit_message_text(
        chat_id=callback.from_user.id,
        message_id=bot_msg_id,
        text=help_text
    )


@auth_router.callback_query(F.data == 'cancel_group_search')
async def handle_cancelling_group_search(callback: CallbackQuery, state: FSMContext):
    # Если данные о пользователе есть — значит возвращаем в меню избранных групп. Нет — в главное меню
    fsm_data = await state.get_data()
    if await DB.is_user_authorized(callback.from_user.id) and fsm_data.get('favorites_request'):
        await favorite_groups_menu(callback, state)
    else:
        await handle_start_command(callback, state)


def search_query_text_process(q: str):
    q = q.upper()
    q = q.replace(' ', '')
    q = q.replace('-', '')
    return q
