from contextlib import suppress
from typing import Optional

from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InputMediaPhoto

from config_reader import graphics
from keyboards import KB
from modules.api_client import API_UNAVAILABLE_TEXT, get_teacher_schedule_flat, search_teachers
from modules.schudule_parser import month_ru_loc, weekday_ru_loc, form_superscript, form_lesson_number, \
    is_teacher_warning_date
from states import TeacherViewer

teachers_router = Router()
TEACHER_SEARCH_WARNING_TEXT = ("\u203c\ufe0f <b>Данные могут быть неверными вследствие проведения сессии! "
                               "Уточняйте информацию у преподавателя</b>\n\n")


@teachers_router.callback_query(F.data == 'teachers')
async def handle_teachers_button(callback: CallbackQuery, state: FSMContext):
    await state.set_state(TeacherViewer.requesting_surname)
    fsm_data = await state.get_data()

    msg_text = (
        f'{TEACHER_SEARCH_WARNING_TEXT if await is_teacher_warning_date() else ""}'
        'Узнайте в какие дни и где можно найти преподавателя\n\n'
        '<i>\u26a0\ufe0f Это <u>не расписание пересдач</u> и отработок '
        '— такую информацию уточняйте лично или на стендах кафедры</i>\n\n'
        '\U0001f447 Введите <u>фамилию</u> преподавателя'
    )

    graphics_media = InputMediaPhoto(media=graphics.teachers_search)
    with suppress(TelegramBadRequest):
        await callback.bot.edit_message_media(
            chat_id=callback.from_user.id, message_id=fsm_data.get('photo_msg_id'), media=graphics_media
        )

    bot_msg = await callback.message.edit_text(text=msg_text, reply_markup=KB.back_to_schedule())
    await state.update_data(bot_msg_id=bot_msg.message_id)


@teachers_router.message(StateFilter(TeacherViewer.requesting_surname))
async def handle_surname(message: Message, state: FSMContext):
    surname = message.text
    await message.delete()

    data = await state.get_data()
    bot_msg_id = data.get('bot_msg_id')
    reply_markup = KB.back_to_schedule()

    if len(surname) < 3:
        text = '\u26a0\ufe0f Запрос слишком короткий. Введите фамилию преподавателя'
    else:
        search_resp = await search_teachers(surname)
        if search_resp is None:
            text = API_UNAVAILABLE_TEXT
        elif not search_resp:
            text = '\u26a0\ufe0f Поиск не дал результатов — проверьте написание <b><u>фамилии</u></b>'
        else:
            await state.update_data(teachers_list=search_resp)
            text = '\U0001f50d Выберите преподавателя'
            reply_markup = KB.teachers_search_results(search_resp)

    await message.bot.edit_message_text(
        chat_id=message.from_user.id,
        message_id=bot_msg_id,
        text=text,
        reply_markup=reply_markup,
    )


@teachers_router.callback_query(F.data.startswith('select_teacher'))
async def handle_teacher_schedule(callback: CallbackQuery, state: FSMContext, teacher_name: Optional[str] = None):
    fsm_data = await state.get_data()
    user_id = callback.from_user.id

    if teacher_name:  # По нажатию из расписания
        teachers_list = [teacher_name]
        teacher = teacher_name
        await state.update_data(teachers_list=teachers_list)
    else:
        teacher_idx = int(callback.data.split('=')[1])
        teachers_list = fsm_data.get('teachers_list', [])
        teacher = teachers_list[teacher_idx]

    search_resp = await get_teacher_schedule_flat(teacher)
    if search_resp is None:
        await callback.answer(API_UNAVAILABLE_TEXT, show_alert=True)
        return

    message_text = f'{TEACHER_SEARCH_WARNING_TEXT if await is_teacher_warning_date() else ""}' \
                   f'<blockquote>Расписание преподавателя <u>{teacher}</u></blockquote>\n'
    last_weekday = ''
    current_day_key = None
    day_index = 0
    for work_day in search_resp:
        lesson_date = f'{int(work_day["lessonDate"][8:])}' + ' ' + f'{month_ru_loc[int(work_day["lessonDate"][5:-3])]}'
        weekday = weekday_ru_loc[work_day['weekday']]
        msg_date_str = f"<b>{weekday} | {lesson_date}</b>\n"

        day_key = (work_day['weekday'], work_day['lessonDate'])
        if day_key != current_day_key:
            current_day_key = day_key
            day_index = 0
        day_index += 1

        subscripts = form_superscript(time_str=work_day['endAt'][:-3], building=work_day["building"])
        formed_end_time = subscripts[0]
        formed_building = subscripts[1]

        is_lecture_emoji = '\U0001f4d6' if work_day['isLecture'] else '\U0001f52c'
        classroom_data = f'{work_day["classroom"]}{formed_building}' if work_day['building'] != 'ДОТ' else 'ДОТ'
        lesson_emoji = form_lesson_number(work_day['startAt'][:-3], work_day['building'], day_index)

        if last_weekday != weekday:
            last_weekday = weekday
            message_text += '\n'
        else:
            msg_date_str = ''
        message_text += (
            f"{msg_date_str}{lesson_emoji}|{is_lecture_emoji}|"
            f"{work_day['startAt'][:-3]}{formed_end_time} | {classroom_data}\n"
        )

    graphics_media = InputMediaPhoto(media=graphics.teachers_schedule)

    # Обработка нажатия фамилии из расписания
    photo_msg_id = fsm_data.get('photo_msg_id')
    with suppress(TelegramBadRequest):
        await callback.bot.edit_message_media(
            chat_id=user_id,
            message_id=photo_msg_id,
            media=graphics_media
        )
    bot_msg_id = fsm_data.get('bot_msg_id')
    await callback.bot.edit_message_text(
        chat_id=user_id,
        message_id=bot_msg_id,
        text=message_text,
        reply_markup=KB.back_to_schedule()
    )
