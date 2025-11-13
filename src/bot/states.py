from aiogram.fsm.state import State, StatesGroup

class RegisterState(StatesGroup):
    waiting_for_address = State()
    waiting_for_private_key = State()
    reset_address = State()
    reset_private_key = State()
    waiting_for_api_key = State()
    waiting_for_api_secret = State()
    waiting_for_api_passphrase  = State()


class TrackSettings(StatesGroup):
    waiting_for_new_wallet = State()
    waiting_for_delete_wallet = State()

class CopyTradeState(StatesGroup):
    selecting_wallet = State()
    setting_duration = State()
    setting_min_amount = State()
    setting_first_bet = State()
    setting_min_quote = State()
    setting_max_quote = State()
    setting_margin = State()  
    confirming_settings = State()
    monitoring = State()
    setting_custom_margin = State()