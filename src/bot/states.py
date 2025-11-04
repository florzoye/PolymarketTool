from aiogram.fsm.state import StatesGroup, State

class RegisterState(StatesGroup):
    waiting_for_address = State()
    reset_address = State()

class TrackSettings(StatesGroup):
    waiting_for_count = State()
    waiting_for_min_value = State()
    waiting_for_new_wallet = State()
    waiting_for_delete_wallet = State()
