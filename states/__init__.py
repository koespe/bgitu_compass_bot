from aiogram.fsm.state import StatesGroup, State


class AuthState(StatesGroup):
    requesting_group_name = State()
