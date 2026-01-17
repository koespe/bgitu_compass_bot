import datetime
from typing import Optional

import aiohttp
from cachetools import TTLCache

from config_reader import config
from database.base import DB

weekday_en_loc = ['', 'MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY', '']
weekday_ru_loc = ['', 'ПН', 'ВТ', 'СР', 'ЧТ', 'ПТ', 'СБ']
weekday_ru_loc_long = ['', 'Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота']
month_ru_loc = ['', 'января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября',
                'ноября', 'декабря']

swap_cache = TTLCache(maxsize=2, ttl=300)  # Кеш API для логики SWAP_WEEKS


def get_week_range(offset=0):
    # Используется только для weekly view
    today = datetime.date.today()
    start_of_week = today - datetime.timedelta(days=today.isoweekday() - 1)
    start_of_week += datetime.timedelta(weeks=offset)
    end_of_week = start_of_week + datetime.timedelta(days=5)
    week_number = start_of_week.isocalendar().week
    return [start_of_week, end_of_week, week_number]


async def handle_group_not_found_error(user_id: int, bot=None):
    """
    Обрабатывает ошибку 409 - группа не найдена.
    Удаляет данные пользователя и возвращает сообщение о необходимости выбрать новую группу.
    """
    await DB.logout(user_id)
    
    message_text = (
        "❌ <b>Ваша группа не найдена в расписании</b>\n\n"
        "Возможно, группа была расформирована или изменена.\n"
        "Пожалуйста, выберите новую группу.\n\n"
        "Вы были возвращены в главное меню."
    )
    
    if bot:
        # Если передан бот, отправляем сообщение
        await bot.send_message(
            chat_id=user_id,
            text=message_text
        )
    
    return message_text


async def api_get_schedule(group_id: int):
    async with aiohttp.ClientSession() as session:
        req_lessons = await session.get(
            url=config.api_host + 'v2/lessons' + f'?groupId={group_id}')
        
        if req_lessons.status == 409:
            return {"error": "group_not_found", "status": 409}
        
        schedule = await req_lessons.json()

        """
        {
          "first_week": {
            "MONDAY": [
              {
                "subjectId": 1094,
                "subjectName": "Физкультура и спорт",
                "building": "1",
                "startAt": "08:20:00",
                "endAt": "09:55:00",
                "classroom": "",
                "teacher": "",
                "isLecture": false
              },
        """
        return schedule


async def form_schedule_message(user_id: int, offset: int = 0,
                                favorite_group_id: Optional[int] = None, favorite_group_name: Optional[str] = None):
    user_data = await DB.user_data(user_id)
    view: str = user_data.get('last_schedule_view')
    message_text = ''

    group_id = user_data.get('group_id') if favorite_group_id is None else favorite_group_id
    schedule = await api_get_schedule(group_id=group_id)
    
    # Проверяем на ошибку 409
    if schedule.get("error") == "group_not_found" and schedule.get("status") == 409:
        if favorite_group_id is None:
            # Это основная группа пользователя - удаляем данные и возвращаем специальное сообщение
            await handle_group_not_found_error(user_id)
            return "GROUP_NOT_FOUND_ERROR"
        else:
            # Это избранная группа - просто возвращаем сообщение об ошибке
            return f"❌ Группа {favorite_group_name} не найдена в расписании"

    if view == 'weekly':
        cur_week_text = ' текущую' if offset == 0 else ''
        dates = get_week_range(offset)  # [start_of_week, end_of_week, week_number]
        current_date = dates[0]

        week_type_for_string = await get_week_type(dates[1], with_swaps=True)
        week_number = "1" if week_type_for_string == "first_week" else "2"
        # Главный header
        date_info = (f'<b>\U0001f5d3\ufe0f Расписание на{cur_week_text} {week_number}ю неделю '
                     f'({dates[0].strftime("%d.%m")} — {dates[1].strftime("%d.%m")})</b>\n\n')

        week_type = await get_week_type(dates[1], with_swaps=False)
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
                teacher = lesson["teacher"]
                subject_name = lesson["subjectName"]

                is_lecture_emoji = '\U0001f4d6' if lesson['isLecture'] else '\U0001f52c'
                classroom_data = f'{classroom}{building}' if building != 'ДОТ' else 'ДОТ'
                teacher = f'({teacher})' if teacher else ''

                str_lessons_data += (f"[{is_lecture_emoji}] {start_time}{end_time} | {classroom_data}\n"
                                     f"<b>{subject_name}</b> {teacher}\n")
            if str_lessons_data:  # Если день не пустой
                message_text += date_str + str_lessons_data + '\n'
        if message_text:
            message_text = date_info + message_text + date_info  # Делаем header и footer c датой

    else:
        date = datetime.date.today() + datetime.timedelta(days=offset)

        week_type_for_string = await get_week_type(date, with_swaps=True)
        cur_day_text = ' Сегодня |' if offset == 0 else ''
        week_number = "1" if week_type_for_string == "first_week" else "2"
        date_info = (f'<blockquote><b>{cur_day_text} {date.strftime("%A").capitalize()}</b> | {date.strftime("%d %B")} '
                     f'| {week_number}я неделя</blockquote>\n\n')

        week_type = await get_week_type(date, with_swaps=False)
        lessons_data: list = schedule.get(week_type).get(weekday_en_loc[date.weekday() + 1])
        if not lessons_data:
            message_text = ''
            return message_text

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
            teacher = lesson["teacher"]
            subject_name = lesson["subjectName"]

            is_lecture_emoji = '\U0001f4d6' if lesson['isLecture'] else '\U0001f52c'
            classroom_data = f'{classroom}{building}' if building != 'ДОТ' else 'ДОТ'
            teacher = f'({teacher})' if teacher else ''

            str_lessons_data += (f"[{is_lecture_emoji}] {start_time}{end_time} | {classroom_data}\n"
                                 f"<b>{subject_name}</b> {teacher}\n")
        if str_lessons_data:  # Если день не пустой
            message_text = date_info + str_lessons_data

    if (favorite_group_name is not None) and len(message_text) != 0:
        message_text = (f'<blockquote>\u26a0\ufe0f <b>Вы просматриваете группу</b> '
                        f'<u>{favorite_group_name}</u></blockquote>\n') + message_text

    return message_text


async def get_week_type(current_date: datetime.date, with_swaps: bool) -> str:
    """
    Надо использовать SWAP_WEEKS для обозначения недели в UI
    Но для формирования расписания использовать алгоритм без логики SWAP_WEEKS
    """
    swap_weeks_flag = False

    if with_swaps:
        if 'flag' in swap_cache:
            swap_weeks_flag = swap_cache['flag']
        else:
            async with aiohttp.ClientSession() as session:
                response = await session.get(config.api_host + 'remoteConfig')
                if response.status == 200:
                    data = await response.json()
                    swap_weeks_flag = data.get('swapWeeks')
            swap_cache['flag'] = swap_weeks_flag

    start_year = current_date.year - 1 if current_date.month < 9 else current_date.year
    start_date = datetime.date(start_year, 9, 1)

    if start_date.isoweekday() == 7:
        start_date += datetime.timedelta(days=1)

    week_num = ((current_date - start_date).days // 7) + 1

    is_second = (week_num % 2 == 0) != swap_weeks_flag
    return "second_week" if is_second else "first_week"


# Текст верхнего регистра
def form_superscript(time_str: str, building: str) -> list:
    s = '⁰¹²³⁴⁵⁶⁷⁸⁹·ᴷ'
    new_time = s[int(time_str[0])] + s[int(time_str[1])] + s[-2] + s[int(time_str[3])] + s[int(time_str[4])]
    if building != 'ДОТ':
        new_building = s[-1] + s[int(building[0])]
    else:
        new_building = building
    return [new_time, new_building]
