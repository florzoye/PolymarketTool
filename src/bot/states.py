from aiogram.fsm.state import State, StatesGroup


class RegisterState(StatesGroup):
    """Состояния регистрации"""
    waiting_for_address = State()
    waiting_for_private_key = State()
    waiting_for_api_key = State()
    waiting_for_api_secret = State()
    waiting_for_api_passphrase = State()
    reset_address = State()
    reset_private_key = State()


class TrackSettings(StatesGroup):
    """Состояния настройки трекинга"""
    waiting_for_new_wallet = State()
    waiting_for_delete_wallet = State()


class CopyTradeState(StatesGroup):
    """Состояния copy-trade"""
    setting_custom_min_amount = State()
    setting_custom_margin = State()
    setting_min_quote = State()
    setting_max_quote = State()
    monitoring = State()