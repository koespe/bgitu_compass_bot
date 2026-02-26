import asyncio
from contextlib import suppress
from typing import Union

import aiohttp
from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, Update, InputMediaPhoto
from aiogram.utils.markdown import hlink

from config_reader import config, graphics_id
from database.base import DB
from handlers.users.favorite_groups import favorite_groups_menu
from handlers.users.main_menu import handle_schedule
from keyboards import KB
from states import AuthState, SupportWordsState

auth_router = Router()


@auth_router.message(CommandStart())
async def handle_start_command(update: Union[Message, CallbackQuery, Update], state: FSMContext):
    await state.clear()

    if await DB.is_user_authorized(update.from_user.id):
        await handle_schedule(update, state)
        return

    welcome_text = (
        'Этот бот поможет узнать <b>расписание групп бакалавриата, СПО и магистратуры</b>\n\n'
        '\u26a1 Удобное <b>приложение для Android</b> → bgitu-compass.ru'
    )

    # Обработка нужна потому что функция может быть вызвана если не нашлась группа (GROUP_NOT_FOUND_ERROR)
    if isinstance(update, Message):
        photo_msg = await update.answer_photo(photo=graphics_id['start_menu'])
        await state.update_data(photo_msg_id=photo_msg.message_id)
        await update.answer(text=welcome_text, reply_markup=KB.start_menu())
    else:
        fsm_data = await state.get_data()
        try:
            await update.bot.edit_message_media(
                chat_id=update.from_user.id,
                message_id=fsm_data.get('photo_msg_id'),
                media=InputMediaPhoto(media=graphics_id['start_menu']),
            )
        except TelegramBadRequest:
            pass
        await update.message.edit_text(text=welcome_text, reply_markup=KB.start_menu())


@auth_router.callback_query(F.data == 'about')
async def about_project(callback: CallbackQuery):
    about_text = (
        'Этот <b>неофициальный</b> бот использует файлы расписания с сайта bgitu.ru — предоставляется расписание для '
        'групп <b><u>БАК, СПО и МАГ</u></b>\n'
        '\U0001f4f1 Также есть <b>приложение для Android</b> → bgitu-compass.ru\n\n'
        '\U0001f464 <b>Разработчик:</b> студент ПрИ-301 — <b>Пудов Кирилл (@koespe)</b>\n'
        '\U0001f464 <b>Разработчик приложения:</b> студент ПрИ-301 — <b>Елисей Веревкин (@Injent)</b>\n'
    )
    await callback.message.edit_text(text=about_text, reply_markup=KB.start_menu(is_about=True))


@auth_router.callback_query(F.data.in_({'choose_group', 'choose_teacher'}))
async def handle_search_setup(callback: CallbackQuery, state: FSMContext):
    is_group = callback.data == 'choose_group'
    next_state = AuthState.requesting_group_name if is_group else AuthState.requesting_teacher_name
    img_key = 'group_search' if is_group else 'teachers_search'
    text = (
        '\U0001f447 Введите группу (можно неполностью)\nПример: «ИСТ», «АД СПО» или «ЭКОНм»'
        if is_group
        else '\U0001f447 Введите фамилию преподавателя (можно неполностью)\nПример: «Казаков»'
    )

    data = await state.get_data()
    if data.get('offset') is not None:
        await state.update_data(old_user=True)

    await state.set_state(next_state)
    with suppress(TelegramBadRequest):
        await callback.bot.edit_message_media(
            chat_id=callback.from_user.id,
            message_id=data.get('photo_msg_id'),
            media=InputMediaPhoto(media=graphics_id[img_key]),
        )

    msg = await callback.message.edit_text(text=text, reply_markup=KB.cancel_group_search())
    await state.update_data(bot_msg_id=msg.message_id)


@auth_router.message(StateFilter(AuthState.requesting_group_name, AuthState.requesting_teacher_name))
async def handle_search_results(message: Message, state: FSMContext):
    current_state = await state.get_state()
    is_group = current_state == AuthState.requesting_group_name

    search_query = message.text
    modified_query = search_query_text_process(search_query)

    fsm_data = await state.get_data()
    bot_msg_id = fsm_data.get('bot_msg_id')

    await message.delete()  # Поисковый запрос пользователя

    endpoint = 'groups' if is_group else 'teacherSchedule'
    async with aiohttp.ClientSession() as web_session:
        url = f'{config.api_host}{endpoint}?searchQuery={modified_query}'
        async with web_session.get(url=url) as search_req:
            search_resp = await search_req.json()

    if not search_resp:
        if is_group:
            text = (
                f'\U0001f914 По запросу "{search_query}" ничего не нашлось.\n\n'
                'Бот отображает <b>только группы бакалавриата, магистратуры и СПО</b>\n\n'
                'Если вы <b>БАК или СПО</b> — проверьте написание группы '
                '(для СПО необходимо писать "АД СПО" <u>или просто "СПО"</u>).\n\n'
                '\U0001f447 Введите новый запрос ниже'
            )
        else:
            text = (
                f'\U0001f914 По запросу "{search_query}" ничего не нашлось.\n\n'
                'Проверьте правильность написания фамилии преподавателя.\n'
                'Возможно буква «Е» на самом деле «Ё»\n\n'
                '\U0001f447 Введите новый запрос ниже'
            )

        await message.bot.edit_message_text(chat_id=message.from_user.id, message_id=bot_msg_id, text=text)
    else:  # Успешный поиск
        success_text = 'Выберите группу \U0001f447 ' if is_group else 'Выберите преподавателя \U0001f447 '
        kb = KB.groups_search_results(search_resp) if is_group else KB.teacher_search_results(search_resp)
        await message.bot.edit_message_text(
            chat_id=message.from_user.id, message_id=bot_msg_id, text=success_text, reply_markup=kb
        )


@auth_router.callback_query(F.data.startswith(('select_group', 'select_teacher_main')))
async def bind_entity_to_user(callback: CallbackQuery, state: FSMContext):
    fsm_data = await state.get_data()
    is_group = callback.data.startswith('select_group')
    user_id = callback.from_user.id

    # 1. Парсим данные
    if is_group:
        parts = callback.data.split('_')
        group_id, entity_name = int(parts[2]), parts[3]
    else:
        entity_name = callback.data.split('=')[1]

    # 2. Обработка "Избранного"
    if is_group and fsm_data.get('favorites_request'):
        await DB.manage_favorites(action='add', user_id=user_id, group_id=group_id)
        await state.set_state(state=None)
        await state.update_data(favorites_request=None)
        await favorite_groups_menu(callback, state)
        return

    # 3. Регистрация
    if fsm_data.get('old_user'):
        await DB.logout(user_id)

    if is_group:
        await DB.add_user(user_id=user_id, group_name=entity_name, group_id=group_id)
    else:
        await DB.add_user(user_id=user_id, teacher_name=entity_name)

        await callback.bot.send_message(
            chat_id=config.admin_tg_id, text=f'Новый преподаватель: {entity_name}, @{callback.from_user.username}'
        )

    # 4. Чистка интерфейса (удаляем картинку и сообщение с кнопками)
    if photo_msg_id := fsm_data.get('photo_msg_id'):
        await callback.bot.delete_message(chat_id=user_id, message_id=photo_msg_id)
    await callback.message.delete()

    # 5. Подтверждение и Онбординг
    role_text = 'группу' if is_group else 'преподавателя'
    await callback.message.answer(f'Вы выбрали {role_text} {entity_name}')
    await asyncio.sleep(1)

    if not fsm_data.get('old_user'):
        extra_line = (
            '\n👤 Расписание преподавателей — узнайте в 2 клика, где можно найти преподавателя\n' if is_group else ''
        )

        onboarding_text_1 = (
            f'✍️ <b>Быстрый экскурс в бота</b>\n\n'
            f'📖 — <b>лекция</b>\n'
            f'🔬 — <b>практика</b>\n'
            f'{extra_line}\n'
            f'🗣️ Если есть предложения/замечания — пишите мне! @koespe'
        )

        onboarding_text_2 = hlink(
            "\u2764\ufe0f Добавьте ярлык на IOS для быстрого доступа", "https://telegra.ph/Dostup-odnoj-knopkoj-IOS-01-30"
        )

        await callback.message.answer(onboarding_text_1)
        await asyncio.sleep(3)
        await callback.message.answer(onboarding_text_2)
        await asyncio.sleep(3)

    # 6. Отправляем расписание
    await state.clear()
    await state.update_data(refresh=True)
    await handle_schedule(callback, state)


@auth_router.callback_query(F.data == 'cancel_group_search')
async def handle_cancelling_group_search(callback: CallbackQuery, state: FSMContext):
    # Если данные о пользователе есть — значит возвращаем в меню избранных групп. Нет — в главное меню
    fsm_data = await state.get_data()
    if await DB.is_user_authorized(callback.from_user.id) and fsm_data.get('favorites_request'):
        await favorite_groups_menu(callback, state)
    else:
        await handle_start_command(callback, state)


@auth_router.message(CommandStart(deep_link=True, magic=F.args == "support_words"))
async def handle_support_words(message: Message, state: FSMContext):
    msg_text = (
        '\U0001f917 Вы можете поддержать разработчиков теплыми словами, им будет очень приятно!\n'
        'Напишите одно сообщение'
    )
    await message.answer(msg_text)
    await state.set_state(SupportWordsState.waiting_for_msg)


@auth_router.message(StateFilter(SupportWordsState.waiting_for_msg))
async def send_support_words(message: Message, state: FSMContext):
    await message.answer('Спасибо за поддержку!')
    await message.forward(chat_id=198685526)
    await state.set_state(state=None)


def search_query_text_process(q: str):
    q = q.upper()
    q = q.replace(' ', '')
    q = q.replace('-', '')
    return q
