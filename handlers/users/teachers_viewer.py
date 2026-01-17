import datetime

import aiohttp
from aiogram import Router, F, Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, Update, InputMediaPhoto, InlineKeyboardButton
from aiogram.filters import StateFilter
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config_reader import config, graphics_id
from keyboards import KB
from modules.schudule_parser import month_ru_loc, weekday_ru_loc, form_superscript

teachers_router = Router()


class TeacherViewer(StatesGroup):
    requesting_surname = State()


@teachers_router.callback_query(F.data == 'teachers')
async def unavailable_button(callback: CallbackQuery, state: FSMContext):
    await callback.answer(text='Функция недоступна: пока что нет расписания для ВСЕХ групп',
                          show_alert=True)


# @teachers_router.callback_query(F.data == 'teachers')
# async def handle_teachers_button(callback: CallbackQuery, state: FSMContext):
#     await state.set_state(TeacherViewer.requesting_surname)
#     fsm_data = await state.get_data()
#
#     msg_text = ('Узнайте в какие дни и где можно найти преподавателя\n\n'
#                 '<i>\u26a0\ufe0f Это <u>не расписание пересдач</u> и отработок — такую информацию уточняйте лично или на стендах кафедры</i>\n\n'
#                 '\U0001f447 Введите <u>фамилию</u> преподавателя')
#
#     # Картинку обновляем
#     graphics = InputMediaPhoto(media=graphics_id['teachers_search'])
#     try:
#         await callback.bot.edit_message_media(
#             chat_id=callback.from_user.id,
#             message_id=fsm_data.get('photo_msg_id'),
#             media=graphics
#         )
#     except TelegramBadRequest:
#         pass
#
#     bot_msg = await callback.message.edit_text(
#         text=msg_text,
#         reply_markup=KB.back_to_schedule()
#     )
#     await state.update_data(bot_msg_id=bot_msg.message_id)


@teachers_router.message(StateFilter(TeacherViewer.requesting_surname))
async def handle_surname(message: Message, state: FSMContext):
    surname = message.text
    await message.delete()

    if len(surname) < 3:
        await message.bot.edit_message_text(
            chat_id=message.from_user.id,
            message_id=(await state.get_data()).get('bot_msg_id'),
            text='\u26a0\ufe0f Запрос слишком короткий. Введите фамилию преподавателя',
            reply_markup=KB.back_to_schedule()
        )
        return

    async with aiohttp.ClientSession() as web_session:
        search_req = await web_session.get(url=config.api_host + f'v2/teacherSearch?searchQuery={surname}')
        search_resp: list = await search_req.json()

    if len(search_resp) == 0:
        await message.bot.edit_message_text(
            chat_id=message.from_user.id,
            message_id=(await state.get_data()).get('bot_msg_id'),
            text='\u26a0\ufe0f Поиск не дал результатов — проверьте написание <b><u>фамилии</u></b>',
            reply_markup=KB.back_to_schedule()
        )
        return

    teachers_kb = KB.teachers_search_results(search_resp)
    await message.bot.edit_message_text(
        chat_id=message.from_user.id,
        message_id=(await state.get_data()).get('bot_msg_id'),
        text='\U0001f50d Выберите преподавателя',
        reply_markup=teachers_kb
    )


@teachers_router.callback_query(F.data.startswith('select_teacher'))
async def handle_teacher_schedule(callback: CallbackQuery, state: FSMContext):
    teacher = callback.data.split('=')[1]

    date_from = datetime.datetime.today().strftime('%Y-%m-%d')
    date_to = (datetime.datetime.today() + datetime.timedelta(days=15)).strftime('%Y-%m-%d')
    async with aiohttp.ClientSession() as web_session:
        search_req = await web_session.get(url=config.api_host + f'v2/teacherSearch?teacher={teacher}&'
                                                                 f'dateFrom={date_from}&dateTo={date_to}')
        search_resp: list = await search_req.json()
    print(date_from, date_to)
    print(search_resp)
    message_text = f'<blockquote>Расписание преподавателя <u>{teacher}</u></blockquote>\n'
    last_weekday = ''
    for work_day in search_resp:
        lesson_date = f'{int(work_day["lessonDate"][8:])}' + ' ' + f'{month_ru_loc[int(work_day["lessonDate"][5:-3])]}'
        weekday = weekday_ru_loc[work_day['weekday']]
        msg_date_str = f"<b>{weekday} | {lesson_date}</b>\n"

        subscripts = form_superscript(time_str=work_day['endAt'][:-3],
                                      building=work_day["building"])
        formed_end_time = subscripts[0]
        formed_building = subscripts[1]

        is_lecture_emoji = '\U0001f4d6' if work_day['isLecture'] else '\U0001f52c'
        classroom_data = f'{work_day["classroom"]}{formed_building}' if work_day['building'] != 'ДОТ' else 'ДОТ'

        if last_weekday != weekday:
            last_weekday = weekday
            message_text += '\n'
        else:
            msg_date_str = ''
        message_text += (f"{msg_date_str}"
                         f"[{is_lecture_emoji}] {work_day['startAt'][:-3]}{formed_end_time} | {classroom_data}\n")

    fsm_data = await state.get_data()
    graphics = InputMediaPhoto(media=graphics_id['teachers_schedule'])
    try:
        await callback.bot.edit_message_media(
            chat_id=callback.from_user.id,
            message_id=fsm_data.get('photo_msg_id'),
            media=graphics
        )
    except TelegramBadRequest:
        pass

    await callback.message.edit_text(
        text=message_text,
        reply_markup=KB.back_to_schedule()
    )
