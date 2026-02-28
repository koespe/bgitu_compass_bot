from aiogram.fsm.state import StatesGroup, State


class AuthState(StatesGroup):
    requesting_group_name = State()
    requesting_teacher_name = State()


class SupportWordsState(StatesGroup):
    waiting_for_msg = State()


class Broadcast(StatesGroup):
    requesting_message = State()
    requesting_list_id = State()
    requesting_ad_data = State()


class AdMessage(StatesGroup):
    requesting_message = State()


class TeacherViewer(StatesGroup):
    requesting_surname = State()
