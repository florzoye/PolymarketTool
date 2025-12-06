from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_main_menu_keyboard():
    """Главное меню"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='📊 Мои позиции', callback_data='show_positions')],
            [InlineKeyboardButton(text='🏆 Рейтинг', callback_data='show_leaderboard')],
            [InlineKeyboardButton(text='🔄 Сменить кошелек', callback_data='reset_wallet')],
            [InlineKeyboardButton(text='📋 Copy Trade', callback_data='copy_trade_menu')]
        ]
    )


def get_copy_trade_menu_keyboard():
    """Меню copy-trade"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='Кошельки на треке', callback_data='track_wallets')],
            [InlineKeyboardButton(text='Позиции кошельков на треке', callback_data='track_positions')],
            [InlineKeyboardButton(text='Запустить copy-trade для конкретных кошельков', callback_data='start_copy_trade')],
            [InlineKeyboardButton(text='⬅️ Главное меню', callback_data='main_menu')]
        ]
    )


def get_leaderboard_keyboard():
    """Клавиатура выбора периода рейтинга"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='Дневной', callback_data='day_lead')],
            [InlineKeyboardButton(text='Недельный', callback_data='week_lead')],
            [InlineKeyboardButton(text='⬅️ Главное меню', callback_data='main_menu')]
        ]
    )


def get_track_wallets_keyboard():
    """Клавиатура управления кошельками на треке"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='Добавить новый кошелек', callback_data='add_new_track_wallet')],
            [InlineKeyboardButton(text='Удалить кошелек на треке', callback_data='delete_track_wallet')],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="copy_trade_back")]
        ]
    )


def get_positions_keyboard(positions_count: int):
    """Клавиатура для позиций"""
    keyboard = [
        *[
            [InlineKeyboardButton(text=f"📉 График {i+1}", callback_data=f"chart_{i}")]
            for i in range(positions_count)
        ],
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="show_positions")],
        [InlineKeyboardButton(text="❌ Закрыть позицию", callback_data="select_position_to_close")],
        [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_api_setup_keyboard():
    """Клавиатура для настройки API credentials"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, хочу", callback_data="setup_api_yes")],
            [InlineKeyboardButton(text="❌ Пропустить (ограниченный функционал)", callback_data="setup_api_no")]
        ]
    )


def get_monitoring_keyboard():
    """Клавиатура активного мониторинга"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🛑 Остановить мониторинг", callback_data="stop_monitoring")],
            [InlineKeyboardButton(text="📊 Статистика", callback_data="monitoring_stats")]
        ]
    )


def get_back_button(callback_data: str = "main_menu"):
    """Простая кнопка назад"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=callback_data)]
        ]
    )