import datetime

from apscheduler.jobstores.redis import RedisJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from database.base import get_session

lessons_time = ['8:20-9:55', '10:05-11:40', '11:50-13:25', '14:00-15:35', '15:45-17:20',
                '8:50-10:25', '10:35-12:10', '12:20-13:55', '14:30-16:05', '16:15-17:50'
                ]

# jobstores = {'default': RedisJobStore(jobs_key='notification_jobs',
#                                       run_times_key='notification_jobs_running',
#                                       host='localhost',
#                                       db=0,
#                                       port=6379)
#              }

# scheduler = AsyncIOScheduler(jobstores=jobstores)
scheduler = AsyncIOScheduler()


def get_time_list(time_format: str) -> list:
    """
    :param time_format: start, end, all
    :return: Список из [[08:20, ...]]
    """
    return_list = []
    if time_format == 'start':
        for time in lessons_time:
            return_list.append(time.split('-')[0])

    return return_list


# TODO: обработать вс при day_of_week=sunday,

class NotificationSender:
    @staticmethod
    def initialize():
        """
        Эта функция будет вызываться в 04:00 и будет на текущий день планировать уведомления по времени
        """
        #  Идем по таблице Users, группируем по группам
        ...




        # before_lessons and after_lessons and between
        # for i, raw_str in enumerate(lessons_time):
        #     time = raw_str.split('-')
        #     time_start = time[0]
        #     time_end = time[1]
        #     time_start_obj = datetime.datetime.strptime(time_start, '%H:%M')
        #     time_end_obj = datetime.datetime.strptime(time_end, '%H:%M')
        #
        #     minutes_offset = 20
        #     before_lesson_time_trigger = time_start_obj - datetime.timedelta(minutes=minutes_offset)
        #     scheduler.add_job(NotificationSender.before_lessons,
        #                       trigger='cron',
        #                       day_of_week='*',
        #                       hour=before_lesson_time_trigger.hour, minute=before_lesson_time_trigger.minute,
        #                       id=f'before_lessons_{i}',
        #                       kwargs={'trigger_time': time_start})
        #
        #     after_lesson_time_trigger = time_end_obj + datetime.timedelta(minutes=minutes_offset)
        #     scheduler.add_job(NotificationSender.after_lessons,
        #                       trigger='cron',
        #                       day_of_week='*',
        #                       hour=after_lesson_time_trigger.hour, minute=after_lesson_time_trigger.minute,
        #                       id=f'after_lessons_{i}',
        #                       kwargs={'trigger_time': time_start})
        #
        #     # TODO: надо присылать уведомление где первая пара
        #     scheduler.add_job(NotificationSender.between_lessons,
        #                       trigger='cron',
        #                       day_of_week='*',
        #                       hour=time_end_obj.hour, minute=after_lesson_time_trigger.minute,
        #                       id=f'after_lessons_{i}',
        #                       kwargs={'trigger_time': time_start})


        scheduler.start()

    @staticmethod
    async def before_lessons(trigger_time: str):
        """
        Мы берем время начала всех пар -20мин и в это время вызываем эту функцию
        Идем по таблице Users, группируем по группам, смотрим — если время срабатывания — первая пара по счету — отправляем уведомление

        Запускать функцию и в аргументах время
        А инит через time for parse
        """
        timing_minutes: int = 20
        time_for_parse = get_time_list(time_format='start')
        async with get_session() as session:
            for time in time_for_parse:
                time_obj = datetime.datetime.strptime(time, '%H:%M')

    @staticmethod
    async def after_lessons(trigger_time: str):
        minutes_offset: int = 20
        ...

    @staticmethod
    async def between_lessons(trigger_time: str):
        minutes_offset: int = 20
        """
        По окончанию каждой пары присылаю следующую пару
        Как? — ставлю таймерЫ на окончаниие пар и там смотрю каждую группу
        """


    @staticmethod
    async def next_week():
        """
        Расписание на след. неделю в пятницу или субботу
        Как? — 1) в 19:00 пятницу и субботу смотрю у каких групп уже закончились пары на неделе (/lessons?tomorrow)
        """
