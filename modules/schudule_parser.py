import datetime
from typing import Optional

import aiohttp
from aiogram.utils.markdown import hlink
from cachetools import TTLCache

from config_reader import config
from database.base import DB

weekday_en_loc = ['', 'MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY', '']
weekday_ru_loc = ['', 'ПН', 'ВТ', 'СР', 'ЧТ', 'ПТ', 'СБ']
weekday_ru_loc_long = ['', 'Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота']
month_ru_loc = ['', 'января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября',
                'ноября', 'декабря']

term_start_date_cache = TTLCache(maxsize=2, ttl=600)
remote_config_cache = TTLCache(maxsize=2, ttl=600)


async def get_remote_config() -> dict:
    if 'data' in remote_config_cache:
        return remote_config_cache['data']

    async with aiohttp.ClientSession() as session:
        response = await session.get(config.api_host + 'remoteConfig')
        if response.status == 200:
            data = await response.json()
            remote_config_cache['data'] = data
            return data
    return {}


async def api_get_schedule(group_id: int):
    async with aiohttp.ClientSession() as session:
        req_lessons = await session.get(
            url=config.api_host + 'v3/lessons' + f'?groupId={group_id}')

        if req_lessons.status == 409:  # Группа отсутсвует
            return {"status": 409}

        schedule = await req_lessons.json()
        return schedule


async def api_get_teacher_schedule(teacher: str):
    async with aiohttp.ClientSession() as session:
        req_lessons = await session.get(url=config.api_host + 'teacherSchedule' + f'?teacher={teacher}')

        schedule = await req_lessons.json()

        if not any(schedule.get('first_week', {}).values()) and not any(schedule.get('second_week', {}).values()):
            return {"status": 404}

        return schedule


async def form_schedule_message(user_id: int, offset: int = 0,
                                favorite_group_id: Optional[int] = None, favorite_group_name: Optional[str] = None,
                                teacher_name: Optional[str] = None, bot_username: Optional[str] = None) -> tuple[
    str, dict]:
    user_data = await DB.user_data(user_id)
    view: str = user_data.get('last_schedule_view')
    message_text = ''
    teachers_dict = {}  # {teacher_id: teacherFullName}
    teacher_id_counter = 0

    if teacher_name and not favorite_group_id:
        schedule = await api_get_teacher_schedule(teacher_name)
    else:
        group_id = user_data.get('group_id') if favorite_group_id is None else favorite_group_id
        schedule: dict = await api_get_schedule(group_id=group_id)

    # Проверяем на ошибку 409 (группа не найдена)
    if schedule.get("status") == 409:
        return "FAV_GROUP_NOT_FOUND" if favorite_group_id else "GROUP_NOT_FOUND", {}
    if schedule.get("status") == 404:
        return "TEACHER_NOT_FOUND", {}

    if view == 'weekly':
        cur_week_text = ' текущую' if offset == 0 else ''
        dates = get_week_range(offset)  # [start_of_week, end_of_week, week_number]
        current_date = dates[0]

        week_type = await get_week_type(dates[1])
        week_number = "1" if week_type == "first_week" else "2"

        date_info = (f'<b>\U0001f5d3\ufe0f Расписание на{cur_week_text} {week_number}ю неделю '
                     f'({dates[0].strftime("%d.%m")} — {dates[1].strftime("%d.%m")})</b>\n\n')

        for weekday in range(1, 7):
            # Создаем header для дня недели "СБ | 25 января"
            lesson_date = current_date + datetime.timedelta(days=weekday - 1)  # не порчу индекс weekday для локализации
            date_str = f"<blockquote><b>{weekday_ru_loc[weekday]} | {lesson_date.strftime('%d %B')}</b></blockquote>\n"

            lessons_data: list = schedule.get(week_type).get(weekday_en_loc[weekday])
            str_lessons_data = ''
            for lesson in lessons_data:  # Идем по парам на день
                """[emoji] 08:20⁰⁹·⁵⁵ | ДОТ
                Базы данных (Козлова И.Р.)"""
                subscripts = form_superscript(time_str=lesson['endAt'][:-3],
                                              building=lesson["building"])
                start_time = lesson["startAt"][:-3]
                end_time = subscripts[0]
                building = subscripts[1]
                classroom = lesson["classroom"]
                teacher = lesson.get("teacher")
                full_teacher_name = lesson.get("teacherFullName")
                subject_name = lesson["subjectName"]

                is_lecture_emoji = '\U0001f4d6' if lesson['isLecture'] else '\U0001f52c'
                classroom_data = f'{classroom}{building}' if building != 'ДОТ' else 'ДОТ'
                if teacher and bot_username:
                    teacher_link = hlink(teacher,
                                         f"tg://resolve?domain={bot_username}&start=teacher_{teacher_id_counter}")
                    teachers_dict[teacher_id_counter] = full_teacher_name
                    teacher_id_counter += 1
                    teacher = teacher_link
                elif teacher:
                    teacher = f'({teacher})'
                else:
                    teacher = ''

                str_lessons_data += (f"[{is_lecture_emoji}] {start_time}{end_time} | {classroom_data}\n"
                                     f"<b>{subject_name}</b> {teacher}\n")
            if str_lessons_data:  # Если день не пустой
                message_text += date_str + str_lessons_data + '\n'
        if message_text:
            message_text = date_info + message_text + date_info  # Делаем header и footer c датой

    else:
        date = datetime.date.today() + datetime.timedelta(days=offset)

        week_type = await get_week_type(date)
        cur_day_text = ' Сегодня |' if offset == 0 else ''
        week_number = "1" if week_type == "first_week" else "2"
        date_info = (f'<blockquote><b>{cur_day_text} {date.strftime("%A").capitalize()}</b> | {date.strftime("%d %B")} '
                     f'| {week_number}я неделя</blockquote>\n\n')

        lessons_data: list = schedule.get(week_type).get(weekday_en_loc[date.weekday() + 1])
        if not lessons_data:
            return '', teachers_dict

        str_lessons_data = ''
        for lesson in lessons_data:  # Идем по парам на день
            """[emoji] 08:20⁰⁹·⁵⁵ | ДОТ
            Базы данных (Козлова И.Р.)"""
            subscripts = form_superscript(time_str=lesson['endAt'][:-3],
                                          building=lesson["building"])
            start_time = lesson["startAt"][:-3]
            end_time = subscripts[0]
            building = subscripts[1]
            classroom = lesson["classroom"]
            teacher = lesson.get("teacher")
            full_teacher_name = lesson.get("teacherFullName")
            subject_name = lesson["subjectName"]

            is_lecture_emoji = '\U0001f4d6' if lesson['isLecture'] else '\U0001f52c'
            classroom_data = f'{classroom}{building}' if building != 'ДОТ' else 'ДОТ'
            if teacher and bot_username:
                teacher_link = hlink(teacher, f"tg://resolve?domain={bot_username}&start=teacher_{teacher_id_counter}")
                teachers_dict[teacher_id_counter] = full_teacher_name
                teacher_id_counter += 1
                teacher = teacher_link
            elif teacher:
                teacher = f'({teacher})'
            else:
                teacher = ''

            str_lessons_data += (f"[{is_lecture_emoji}] {start_time}{end_time} | {classroom_data}\n"
                                 f"<b>{subject_name}</b> {teacher}\n")
        if str_lessons_data:  # Если день не пустой
            message_text = date_info + str_lessons_data

    if (favorite_group_name is not None) and len(message_text) != 0:
        message_text = (f'<blockquote>\u26a0\ufe0f <b>Вы просматриваете группу</b> '
                        f'<u>{favorite_group_name}</u></blockquote>\n') + message_text

    return message_text, teachers_dict


async def get_week_type(current_date: datetime.date) -> str:
    if 'flag' in term_start_date_cache:
        term_start_date = term_start_date_cache['flag']
    else:
        remote_config = await get_remote_config()
        term_start_date_str = remote_config.get('termStartDate', f"{datetime.date.today().year}-09-01")
        term_start_date = datetime.datetime.strptime(term_start_date_str, "%Y-%m-%d").date()
        term_start_date_cache['flag'] = term_start_date

    week_num = ((current_date - term_start_date).days // 7) + 1
    return "second_week" if week_num % 2 == 0 else "first_week"


async def is_teacher_warning_date() -> bool:
    """
    Проверяет, попадает ли текущая дата в диапазоны предупреждения о преподавателях.
    Формат дат в API: mm-dd (например, ["12-08","02-07"] для 8 декабря — 7 февраля).
    """
    current_date = datetime.date.today()

    remote_config = await get_remote_config()
    date_ranges = remote_config.get('teacherSearchWarningDateRanges', [])
    if not date_ranges:
        return False

    for start_str, end_str in date_ranges:
        start_month, start_day = map(int, start_str.split('-'))
        end_month, end_day = map(int, end_str.split('-'))

        start_date = datetime.date(current_date.year, start_month, start_day)
        end_date = datetime.date(current_date.year, end_month, end_day)

        # Обработка перехода через год (например, декабрь-январь)
        if start_date > end_date:
            # Диапазон пересекает границу года
            if current_date >= start_date or current_date <= end_date:
                return True
        else:
            if start_date <= current_date <= end_date:
                return True

    return False


def get_week_range(offset=0):
    # Используется только для weekly view
    today = datetime.date.today()
    start_of_week = today - datetime.timedelta(days=today.isoweekday() - 1)
    start_of_week += datetime.timedelta(weeks=offset)
    end_of_week = start_of_week + datetime.timedelta(days=5)
    week_number = start_of_week.isocalendar().week
    return [start_of_week, end_of_week, week_number]


# Текст верхнего регистра
def form_superscript(time_str: str, building: str) -> list:
    s = '⁰¹²³⁴⁵⁶⁷⁸⁹·ᴷ'
    new_time = s[int(time_str[0])] + s[int(time_str[1])] + s[-2] + s[int(time_str[3])] + s[int(time_str[4])]
    if building != 'ДОТ':
        new_building = s[-1] + s[int(building[0])]
    else:
        new_building = building
    return [new_time, new_building]
