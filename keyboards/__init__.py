import aiohttp
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config_reader import config
from database.base import DB


class KB:
    @staticmethod
    def start_menu(is_about=False):
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text='\u27a1\ufe0f Выбрать группу', callback_data='choose_group'))
        if not is_about:
            kb.row(InlineKeyboardButton(text='\u2139\ufe0f О проекте', callback_data='about'))
        return kb.as_markup()

    @staticmethod
    def cancel_group_search():
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text='\u21aa\ufe0f Вернуться назад', callback_data='cancel_group_search'))
        return kb.as_markup()

    @staticmethod
    def groups_search_results(groups: list):
        kb = InlineKeyboardBuilder()
        for group in groups:
            group_id = group.get('id')
            group_name = group.get('name')
            kb.add(InlineKeyboardButton(text=group_name, callback_data=f'select_group_{group_id}_{group_name}'))

        kb.add(InlineKeyboardButton(text='\U0001f928 Отсутствует группа?', callback_data='no_mine_group'))
        return kb.adjust(1).as_markup()

    @staticmethod
    async def schedule(user_id: int, offset: int, is_favorite: bool = False):
        user_data = await DB.user_data(user_id)
        last_schedule_view = user_data.get('last_schedule_view')

        change_view_button_text = 'Отображение: на день' if last_schedule_view == 'daily' else 'Отображение: на неделю'

        kb = InlineKeyboardBuilder()

        if offset != 0:
            kb.row(
                InlineKeyboardButton(text='\u2b05\ufe0f', callback_data='schedule_page_prev'),
                InlineKeyboardButton(text='\U0001f504', callback_data='schedule_page_refresh'),
                InlineKeyboardButton(text='\u27a1\ufe0f', callback_data='schedule_page_next')
            )
        else:
            kb.row(
                InlineKeyboardButton(text='\u2b05\ufe0f', callback_data='schedule_page_prev'),
                InlineKeyboardButton(text='\u27a1\ufe0f', callback_data='schedule_page_next')
            )
        kb.row(InlineKeyboardButton(text=change_view_button_text, callback_data='schedule_change_view'))
        if is_favorite:
            kb.row(InlineKeyboardButton(text='\U0001f3e0 Вернуться к своей группе', callback_data='favorite_group_exit'))
        else:
            kb.row(InlineKeyboardButton(text='\u2b50 Избранные группы', callback_data='favorite_groups'))
            kb.row(InlineKeyboardButton(text='\U0001f464 Расписание преподавателей', callback_data='teachers'))
            kb.row(InlineKeyboardButton(text='\u26d1\ufe0f Сообщить об ошибке', url='https://t.me/koespe'))
            kb.row(InlineKeyboardButton(text='\u2699\ufe0f Настройки', callback_data='settings_main'))
        return kb.as_markup()

    @staticmethod
    def back_to_schedule():
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text='\u21aa\ufe0f Вернуться назад', callback_data='back_to_schedule'))
        return kb.as_markup()

    @staticmethod
    def settings():
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text='\U0001f928 Изменить основную группу', callback_data='choose_group'))
        kb.row(InlineKeyboardButton(text='\u26d1\ufe0f Поддержка бота', url='https://t.me/koespe'))
        kb.row(InlineKeyboardButton(text='\u21aa\ufe0f Вернуться назад', callback_data='back_to_schedule'))
        return kb.as_markup()

    @staticmethod
    def teachers_search_results(teachers: list):
        kb = InlineKeyboardBuilder()
        for teacher in teachers:
            kb.row(InlineKeyboardButton(text=teacher, callback_data=f'select_teacher={teacher}'))
        kb.row(InlineKeyboardButton(text='\u21aa\ufe0f Вернуться назад', callback_data='back_to_schedule'))
        return kb.adjust(1).as_markup()

    @staticmethod
    def admin_panel():
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text='Рассылка', callback_data='broadcast'))
        return kb.as_markup()

    @staticmethod
    def broadcast_keyboards():
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text='Обычная рассылка', callback_data='broadcast_kb_none'))
        kb.row(InlineKeyboardButton(text='Рассылка + обновить клаву', callback_data='broadcast_kb_update'))
        return kb.as_markup()

    @staticmethod
    def broadcast_types():
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text='Рассылка всем пользователям', callback_data='broadcast_type=all'))
        kb.row(InlineKeyboardButton(text='Рассылка по ID', callback_data='broadcast_type=id_list'))
        kb.row(InlineKeyboardButton(text='Рекламное сообщение по ID', callback_data='broadcast_type=ad'))
        return kb.as_markup()

    @staticmethod
    def restart_to_schedule():
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text='\u2705 Обновить расписание', callback_data='restart_to_schedule'))
        return kb.as_markup()

    @staticmethod
    def cancel_broadcast():
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text='Отменить рассылку', callback_data='cancel_broadcast'))
        return kb.as_markup()

    @staticmethod
    async def favorites_main_menu(user_id: int, is_deleting: bool = False):
        user_favorite_groups: list = (await DB.user_data(user_id)).get('favorite_groups')

        action_word = 'delete' if is_deleting else 'open'
        kb = InlineKeyboardBuilder()
        async with aiohttp.ClientSession() as web_session:
            for group_id in user_favorite_groups:

                group_name_req = await web_session.get(url=config.api_host + f'groups?groupId={group_id}')
                group_name_resp: dict = await group_name_req.json()
                if group_name_req.status == 200:  # Обработка удаленной группы
                    group_name = group_name_resp[0].get('name')
                    kb.row(InlineKeyboardButton(text=group_name, callback_data=f'favorite_group_{action_word}={group_id}'))
        if not is_deleting:
            kb.row(InlineKeyboardButton(text='+ Добавить группу', callback_data=f'favorite_group_search'))
            if len(user_favorite_groups) > 0:
                kb.row(InlineKeyboardButton(text='– Удалить группу', callback_data='favorite_group_delete_button'))
        kb.row(InlineKeyboardButton(text='\u21aa\ufe0f Вернуться назад', callback_data='back_to_schedule'))
        return kb.as_markup()
