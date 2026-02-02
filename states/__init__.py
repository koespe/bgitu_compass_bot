from aiogram.fsm.state import StatesGroup, State


class AuthState(StatesGroup):
    requesting_group_name = State()
    requesting_teacher_name = State()


class SupportWordsState(StatesGroup):
    waiting_for_msg = State()
