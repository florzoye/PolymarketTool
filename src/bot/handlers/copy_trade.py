import asyncio
from itertools import islice
from src.bot.cfg import users_sql, active_monitors

from aiogram.filters import Command
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from src.bot.states import TrackSettings, CopyTradeState
from src.bot.keyboards import (
    get_copy_trade_menu_keyboard, 
    get_track_wallets_keyboard,
    get_back_button
)

from src.bot.utils.monitoring import start_monitoring_task
from src.core.PolyScrapper import PolyScrapper
from utils.formatters import format_money, format_pnl

router = Router()


@router.message(Command('copy_trade'))
async def cmd_copy_trade(message: types.Message):
    """Команда /copy_trade"""
    await message.answer(
        'Меню copy-trade на Polymarket!', 
        reply_markup=get_copy_trade_menu_keyboard()
    )


@router.callback_query(F.data == "copy_trade_menu")
async def copy_trade_menu(callback: CallbackQuery):
    """Показать меню copy-trade"""
    await callback.message.edit_text(
        'Меню copy-trade на Polymarket!', 
        reply_markup=get_copy_trade_menu_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "copy_trade_back")
async def copy_trade_back(callback: CallbackQuery, state: FSMContext):
    """Возврат в меню copy-trade"""
    await state.clear()
    await callback.message.edit_text(
        "Меню copy-trade на Polymarket!", 
        reply_markup=get_copy_trade_menu_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "track_wallets")
async def wallets_in_track(callback: CallbackQuery):
    """Показать кошельки на треке"""
    tg_id = callback.from_user.id
    track_addresses = await users_sql.get_track_wallets(tg_id)

    if not track_addresses:
        await callback.message.edit_text(
            "К вашему аккаунту не привязаны кошельки для трейкинга.\n"
            "Привяжите их и запустите заново.",
            reply_markup=get_track_wallets_keyboard()
        )
        await callback.answer()
        return

    await callback.answer("⏳ Загружаю данные...")

    text = f"**У вас {len(track_addresses)} кошельков на треке, вот их показатели:**\n\n"
    for i, address in enumerate(track_addresses, 1):
        scrapper = PolyScrapper(address)
        lead_data = await scrapper.check_leaderboard()
        value = await scrapper.get_value_user()

        name = lead_data.get('userName', 'Unknown') if isinstance(lead_data, dict) else str(lead_data)
        rank = lead_data.get('rank', '—') if isinstance(lead_data, dict) else '—'
        pnl = lead_data.get('pnl', 0) if isinstance(lead_data, dict) else 0

        text += (
            f"**{i}. {name} (`{address}`)**\n"
            f"🏆 Rank: {rank}\n"
            f"💸 PnL: `${round(pnl, 3)}`\n"
            f"📊 Value: `${value}`\n"
            f"───────────────────────\n"
        )

    await callback.message.edit_text(
        text, 
        parse_mode="Markdown", 
        reply_markup=get_track_wallets_keyboard()
    )


@router.callback_query(F.data == "add_new_track_wallet")
async def add_new_track_wallet(callback: CallbackQuery, state: FSMContext):
    """Начать добавление кошелька на трек"""
    await callback.message.edit_text(
        "Отправьте адрес кошелька, который хотите добавить на трек:\n"
        "(формат: 0x...)",
        reply_markup=get_back_button("track_wallets")
    )
    await state.set_state(TrackSettings.waiting_for_new_wallet)
    await callback.answer()


@router.message(TrackSettings.waiting_for_new_wallet)
async def add_new_track_wallet_handler(message: types.Message, state: FSMContext):
    """Обработка добавления кошелька"""
    address = message.text.strip()
    tg_id = message.from_user.id

    if not address.startswith("0x") or len(address) != 42:
        await message.answer("⚠️ Это невалидный Ethereum/Polymarket адрес. Попробуй снова.")
        return

    await users_sql.add_track_wallet(tg_id, address)
    await state.clear()
    
    await message.answer(
        f"✅ Кошелек `{address}` добавлен на трек!",
        parse_mode="Markdown",
        reply_markup=get_back_button("track_wallets")
    )


@router.callback_query(F.data == "delete_track_wallet")
async def delete_track_wallet(callback: CallbackQuery, state: FSMContext):
    """Начать удаление кошелька с трека"""
    tg_id = callback.from_user.id
    track_wallets = await users_sql.get_track_wallets(tg_id)
    
    if not track_wallets:
        await callback.message.edit_text(
            "У вас нет кошельков на треке для удаления.",
            reply_markup=get_back_button("track_wallets")
        )
        await callback.answer()
        return
    
    wallet_list = "\n".join([f"`{w}`" for w in track_wallets])
    
    await callback.message.edit_text(
        f"Ваши кошельки на треке:\n\n{wallet_list}\n\n"
        "Отправьте адрес кошелька, который хотите удалить:",
        parse_mode="Markdown",
        reply_markup=get_back_button("track_wallets")
    )
    await state.set_state(TrackSettings.waiting_for_delete_wallet)
    await callback.answer()


@router.message(TrackSettings.waiting_for_delete_wallet)
async def delete_track_wallet_handler(message: types.Message, state: FSMContext):
    """Обработка удаления кошелька"""
    address = message.text.strip()
    tg_id = message.from_user.id

    if not address.startswith("0x") or len(address) != 42:
        await message.answer("⚠️ Это невалидный Ethereum/Polymarket адрес. Попробуй снова.")
        return

    track_wallets = await users_sql.get_track_wallets(tg_id)
    
    if address not in track_wallets:
        await message.answer("⚠️ Этот кошелек не найден в списке отслеживаемых.")
        return

    await users_sql.remove_track_wallet(tg_id, address)
    await state.clear()
    
    await message.answer(
        f"✅ Кошелек `{address}` удален из трека!",
        parse_mode="Markdown",
        reply_markup=get_back_button("track_wallets")
    )


# ============== ПОЗИЦИИ КОШЕЛЬКОВ НА ТРЕКЕ ==============

@router.callback_query(F.data == "track_positions")
async def positions_wallets(callback: CallbackQuery, state: FSMContext):
    """Показать позиции кошельков на треке"""
    tg_id = callback.from_user.id
    track_addresses = await users_sql.get_track_wallets(tg_id)

    if not track_addresses:
        await callback.message.edit_text(
            "К вашему аккаунту не привязаны кошельки для трейкинга.\n"
            "Привяжите их и запустите заново.",
            reply_markup=get_back_button("copy_trade_back")
        )
        await callback.answer()
        return

    await state.update_data(
        count=5,
        min_value=3.0,
        sort_by='CASHPNL'
    )
    
    await show_track_settings_menu(callback.message, state)
    await callback.answer()


async def show_track_settings_menu(message, state: FSMContext):
    """Показывает меню настроек отображения позиций"""
    data = await state.get_data()
    count = data.get('count', 5)
    min_value = data.get('min_value', 3.0)
    sort_by = data.get('sort_by', 'CASHPNL')
    
    sort_names = {
        'CASHPNL': '💰 По PnL',
        'INITIAL': '🆕 Новые позиции',
        'CURRENT': '📊 По текущей стоимости'
    }
    
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=f"📊 Количество: {count}",
                callback_data="change_count"
            )],
            [InlineKeyboardButton(
                text=f"💵 Мин. value: ${min_value}",
                callback_data="change_min_value"
            )],
            [InlineKeyboardButton(
                text=f"Сортировка: {sort_names.get(sort_by, sort_by)}",
                callback_data="change_sort"
            )],
            [InlineKeyboardButton(
                text="✅ Показать позиции",
                callback_data="show_track_positions"
            )],
            [InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data="copy_trade_back"
            )]
        ]
    )
    
    text = (
        "⚙️ **Настройки отображения позиций**\n\n"
        f"📊 Количество позиций: **{count}**\n"
        f"💵 Минимальный value: **${min_value}**\n"
        f"🔄 Сортировка: **{sort_names.get(sort_by, sort_by)}**\n\n"
        "Настройте параметры и нажмите \"Показать позиции\""
    )
    
    await message.edit_text(text, parse_mode="Markdown", reply_markup=kb)


router.callback_query(F.data == "change_count")
async def change_count(callback: CallbackQuery, state: FSMContext):
    """Изменить количество позиций"""
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="3", callback_data="set_count_3"),
                InlineKeyboardButton(text="5", callback_data="set_count_5"),
                InlineKeyboardButton(text="10", callback_data="set_count_10")
            ],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_track_settings")]
        ]
    )
    
    await callback.message.edit_text(
        "Выберите количество позиций для отображения:",
        reply_markup=kb
    )
    await callback.answer()


@router.callback_query(F.data.startswith("set_count_"))
async def set_count(callback: CallbackQuery, state: FSMContext):
    """Сохранить количество позиций"""
    count = int(callback.data.split("_")[-1])
    await state.update_data(count=count)
    await show_track_settings_menu(callback.message, state)
    await callback.answer(f"✅ Количество установлено: {count}")


@router.callback_query(F.data == "change_min_value")
async def change_min_value(callback: CallbackQuery, state: FSMContext):
    """Изменить минимальный value"""
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="$1", callback_data="set_value_1"),
                InlineKeyboardButton(text="$3", callback_data="set_value_3"),
                InlineKeyboardButton(text="$5", callback_data="set_value_5")
            ],
            [
                InlineKeyboardButton(text="$10", callback_data="set_value_10"),
                InlineKeyboardButton(text="$20", callback_data="set_value_20"),
                InlineKeyboardButton(text="$50", callback_data="set_value_50")
            ],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_track_settings")]
        ]
    )
    
    await callback.message.edit_text(
        "Выберите минимальный value позиции:",
        reply_markup=kb
    )
    await callback.answer()


@router.callback_query(F.data.startswith("set_value_"))
async def set_min_value(callback: CallbackQuery, state: FSMContext):
    """Сохранить минимальный value"""
    value = float(callback.data.split("_")[-1])
    await state.update_data(min_value=value)
    await show_track_settings_menu(callback.message, state)
    await callback.answer(f"✅ Минимальный value установлен: ${value}")


@router.callback_query(F.data == "change_sort")
async def change_sort(callback: CallbackQuery, state: FSMContext):
    """Изменить тип сортировки"""
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="💰 По PnL",
                callback_data="set_sort_CASHPNL"
            )],
            [InlineKeyboardButton(
                text="🆕 Новые позиции",
                callback_data="set_sort_INITIAL"
            )],
            [InlineKeyboardButton(
                text="📊 По текущей стоимости",
                callback_data="set_sort_CURRENT"
            )],
            [InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data="back_to_track_settings"
            )]
        ]
    )
    
    await callback.message.edit_text(
        "Выберите тип сортировки позиций:",
        reply_markup=kb
    )
    await callback.answer()


@router.callback_query(F.data.startswith("set_sort_"))
async def set_sort(callback: CallbackQuery, state: FSMContext):
    """Сохранить тип сортировки"""
    sort_by = callback.data.replace("set_sort_", "")
    await state.update_data(sort_by=sort_by)
    
    sort_names = {
        'CASHPNL': 'По PnL',
        'INITIAL': 'Новые позиции',
        'CURRENT': 'По текущей стоимости'
    }
    
    await show_track_settings_menu(callback.message, state)
    await callback.answer(f"✅ Сортировка: {sort_names.get(sort_by, sort_by)}")


@router.callback_query(F.data == "back_to_track_settings")
async def back_to_track_settings(callback: CallbackQuery, state: FSMContext):
    """Возврат к настройкам трека"""
    await show_track_settings_menu(callback.message, state)
    await callback.answer()


@router.callback_query(F.data == "show_track_positions")
async def show_track_positions(callback: CallbackQuery, state: FSMContext):
    """Показать позиции с учетом настроек"""
    tg_id = callback.from_user.id
    data = await state.get_data()
    
    count = data.get('count', 5)
    min_value = data.get('min_value', 3.0)
    sort_by = data.get('sort_by', 'CASHPNL')
    
    track_addresses = await users_sql.get_track_wallets(tg_id)
    
    if not track_addresses:
        await callback.answer("❌ Нет кошельков на треке", show_alert=True)
        return
    
    await callback.answer("⏳ Загружаю позиции...")
    
    sort_names = {
        'CASHPNL': 'PnL',
        'INITIAL': 'новым',
        'CURRENT': 'стоимости'
    }
    
    text = (
        f"📊 **Позиции кошельков на треке**\n"
        f"(топ {count}, min ${min_value}, по {sort_names.get(sort_by, sort_by)})\n\n"
    )

    for address in track_addresses:
        scrapper = PolyScrapper(address)
        leaderboard_data = await scrapper.check_leaderboard()
        name = leaderboard_data.get("userName", "Неизвестный")

        positions = await scrapper.get_account_positions(sortBy=sort_by) or []

        filtered_positions = list(islice(
            (
                p for p in positions
                if float(p.get("currentValue") or 0) >= min_value
                and float(p.get("percentRealizedPnl") or 0) > -90
            ),
            count
        ))

        text += (
            "━━━━━━━━━━━━━━━━━━━\n"
            f"👤 **{name}**\n"
            f"`{address}`\n\n"
        )

        if not filtered_positions:
            text += "❌ Нет подходящих позиций.\n\n"
            continue

        for j, pos in enumerate(filtered_positions, 1):
            title = pos.get("title", "Без названия")
            current = float(pos.get("currentValue") or 0)
            pnl = float(pos.get("cashPnl") or 0)
            percent = float(pos.get("percentRealizedPnl") or 0)

            text += (
                f"{j}️⃣ **{title}**\n"
                f"💰 {format_money(current)} {format_pnl(pnl, percent)}\n\n"
            )

        text += "━━━━━━━━━━━━━━━━━━━\n"

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="show_track_positions")],
            [InlineKeyboardButton(text="⚙️ Настройки", callback_data="back_to_track_settings")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="copy_trade_back")]
        ]
    )
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)


@router.callback_query(F.data == "start_copy_trade")
async def start_copy_trade_flow(callback: CallbackQuery, state: FSMContext):
    """Начало быстрой настройки copy-trade"""
    tg_id = callback.from_user.id
    track_addresses = await users_sql.get_track_wallets(tg_id)
    
    if not track_addresses:
        await callback.message.edit_text(
            "❌ У вас нет кошельков на треке.\n"
            "Сначала добавьте кошельки через меню 'Кошельки на треке'.",
            reply_markup=get_back_button("copy_trade_back")
        )
        await callback.answer()
        return
    
    await state.update_data(
        track_addresses=track_addresses,
        selected_wallet=None,
        duration=3600,
        min_amount=5,
        first_bet=False,
        min_quote=0.01,
        max_quote=1.0,
        margin_amount=10,
        sl_percent=30,
        tp_percent=50
    )
    
    await show_quick_setup_menu(callback.message, state)
    await callback.answer()


async def show_quick_setup_menu(message, state: FSMContext):
    """Показывает меню быстрой настройки"""
    data = await state.get_data()
    
    selected_wallet = data.get("selected_wallet")
    duration = data.get("duration", 3600)
    min_amount = data.get("min_amount", 5)
    first_bet = data.get("first_bet", False)
    min_quote = data.get("min_quote", 0.01)
    max_quote = data.get("max_quote", 1.0)
    margin_amount = data.get("margin_amount", 10)
    sl_percent = data.get("sl_percent", 30)
    tp_percent = data.get("tp_percent", 50)
    
    duration_text = f"{duration // 60} мин" if duration < 3600 else f"{duration // 3600} ч"
    first_bet_text = "✅ Да" if first_bet else "❌ Нет"
    
    wallet_text = "Не выбран"
    if selected_wallet:
        try:
            scrapper = PolyScrapper(selected_wallet)
            lead_data = await scrapper.check_leaderboard()
            name = lead_data.get('userName', 'Unknown') if isinstance(lead_data, dict) else 'Unknown'
            wallet_text = f"{name} ({selected_wallet[:6]}...)"
        except:
            wallet_text = f"{selected_wallet[:6]}...{selected_wallet[-4:]}"
    
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"👛 Кошелек: {wallet_text}", callback_data="quick_select_wallet")],
            [InlineKeyboardButton(text=f"⏱ Длительность: {duration_text}", callback_data="quick_duration")],
            [InlineKeyboardButton(text=f"💰 Мин. сумма: ${min_amount}", callback_data="quick_min_amount")],
            [InlineKeyboardButton(text=f"🎯 Первые ставки: {first_bet_text}", callback_data="quick_first_bet")],
            [InlineKeyboardButton(text=f"📊 Котировки: {min_quote} - {max_quote}", callback_data="quick_quotes")],
            [InlineKeyboardButton(text=f"💵 Маржа: ${margin_amount}", callback_data="quick_margin")],
            [InlineKeyboardButton(text=f"🛑 SL (%): {sl_percent}%", callback_data="quick_sl")],
            [InlineKeyboardButton(text=f"🎯 TP (%): {tp_percent}%", callback_data="quick_tp")],
            [InlineKeyboardButton(text="🚀 Запустить мониторинг", callback_data="quick_start_monitoring")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="copy_trade_back")]
        ]
    )
    
    text = (
        "⚙️ **Быстрая настройка Copy-Trade**\n\n"
        "Нажмите на параметр, чтобы изменить его:\n\n"
        f"👛 **Кошелек:** {wallet_text}\n"
        f"⏱ **Длительность:** {duration_text}\n"
        f"💰 **Мин. сумма ставки:** ${min_amount}\n"
        f"🎯 **Только первые ставки:** {first_bet_text}\n"
        f"📊 **Диапазон котировок:** {min_quote} - {max_quote}\n"
        f"💵 **Маржа на сделку:** ${margin_amount}\n"
        f"🛑 **Stop Loss:** {sl_percent}%\n"
        f"🎯 **Take Profit:** {tp_percent}%\n\n"
        f"Когда всё готово — нажмите '🚀 Запустить мониторинг'"
    )
    
    await message.edit_text(text, parse_mode="Markdown", reply_markup=kb)


@router.callback_query(F.data == "quick_back")
async def quick_back(callback: CallbackQuery, state: FSMContext):
    """Возврат к быстрой настройке"""
    await show_quick_setup_menu(callback.message, state)
    await callback.answer()


@router.callback_query(F.data == "quick_setup_back")
async def quick_setup_back(callback: CallbackQuery, state: FSMContext):
    """Возврат к быстрой настройке"""
    await show_quick_setup_menu(callback.message, state)
    await callback.answer()


# ============== ВЫБОР КОШЕЛЬКА ==============

@router.callback_query(F.data == "quick_select_wallet")
async def quick_select_wallet(callback: CallbackQuery, state: FSMContext):
    """Выбор кошелька"""
    data = await state.get_data()
    track_addresses = data.get("track_addresses", [])
    
    keyboard = []
    for i, address in enumerate(track_addresses):
        try:
            scrapper = PolyScrapper(address)
            lead_data = await scrapper.check_leaderboard()
            name = lead_data.get('userName', 'Unknown') if isinstance(lead_data, dict) else 'Unknown'
        except:
            name = 'Unknown'
        
        keyboard.append([InlineKeyboardButton(
            text=f"{name} ({address[:6]}...{address[-4:]})",
            callback_data=f"qw_{i}"
        )])
    
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="quick_back")])
    
    kb = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    await callback.message.edit_text(
        "👛 **Выберите кошелек для мониторинга:**",
        parse_mode="Markdown",
        reply_markup=kb
    )
    await callback.answer()


@router.callback_query(F.data.startswith("qw_"))
async def quick_wallet_selected(callback: CallbackQuery, state: FSMContext):
    """Сохранение выбранного кошелька"""
    wallet_index = int(callback.data.split("_")[-1])
    data = await state.get_data()
    track_addresses = data.get("track_addresses", [])
    
    if wallet_index < len(track_addresses):
        await state.update_data(selected_wallet=track_addresses[wallet_index])
        await callback.answer("✅ Кошелек выбран")
    
    await show_quick_setup_menu(callback.message, state)


# ============== ВЫБОР ДЛИТЕЛЬНОСТИ ==============

@router.callback_query(F.data == "quick_duration")
async def quick_duration(callback: CallbackQuery, state: FSMContext):
    """Выбор длительности"""
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="5 мин", callback_data="qd_300"),
                InlineKeyboardButton(text="15 мин", callback_data="qd_900")
            ],
            [
                InlineKeyboardButton(text="30 мин", callback_data="qd_1800"),
                InlineKeyboardButton(text="1 час", callback_data="qd_3600")
            ],
            [
                InlineKeyboardButton(text="2 часа", callback_data="qd_7200"),
                InlineKeyboardButton(text="6 часов", callback_data="qd_21600")
            ],
            [
                InlineKeyboardButton(text="12 часов", callback_data="qd_43200"),
                InlineKeyboardButton(text="24 часа", callback_data="qd_86400")
            ],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="quick_back")]
        ]
    )
    
    await callback.message.edit_text(
        "⏱ **Выберите длительность мониторинга:**",
        parse_mode="Markdown",
        reply_markup=kb
    )
    await callback.answer()


@router.callback_query(F.data.startswith("qd_"))
async def quick_duration_selected(callback: CallbackQuery, state: FSMContext):
    """Сохранение длительности"""
    duration = int(callback.data.split("_")[-1])
    await state.update_data(duration=duration)
    
    duration_text = f"{duration // 60} мин" if duration < 3600 else f"{duration // 3600} ч"
    await callback.answer(f"✅ Длительность: {duration_text}")
    
    await show_quick_setup_menu(callback.message, state)


router.callback_query(F.data == "quick_min_amount")
async def quick_min_amount(callback: CallbackQuery, state: FSMContext):
    """Выбор минимальной суммы"""
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="$1", callback_data="qa_1"),
                InlineKeyboardButton(text="$5", callback_data="qa_5"),
                InlineKeyboardButton(text="$10", callback_data="qa_10")
            ],
            [
                InlineKeyboardButton(text="$25", callback_data="qa_25"),
                InlineKeyboardButton(text="$50", callback_data="qa_50"),
                InlineKeyboardButton(text="$100", callback_data="qa_100")
            ],
            [
                InlineKeyboardButton(text="$250", callback_data="qa_250"),
                InlineKeyboardButton(text="$500", callback_data="qa_500")
            ],
            [InlineKeyboardButton(text="✏️ Ввести свою сумму", callback_data="qa_custom")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="quick_back")]
        ]
    )
    
    await callback.message.edit_text(
        "💰 **Выберите минимальную сумму ставки:**\n"
        "(Ставки меньше этой суммы будут игнорироваться)\n\n"
        "Или введите свою кастомную сумму",
        parse_mode="Markdown",
        reply_markup=kb
    )
    await callback.answer()


@router.callback_query(F.data.startswith("qa_"))
async def quick_amount_selected(callback: CallbackQuery, state: FSMContext):
    """Сохранение минимальной суммы"""
    if callback.data == "qa_custom":
        await callback.message.edit_text(
            "✏️ **Ввод кастомной минимальной суммы**\n\n"
            "💰 Введите минимальную сумму ставки в долларах:\n\n"
            "Примеры: `3`, `7.5`, `15`\n\n"
            "⚠️ Минимум: $0.1\n"
            "⚠️ Максимум: $1000\n\n"
            "Отправьте число в чат:",
            parse_mode="Markdown",
            reply_markup=get_back_button("quick_back")
        )
        await state.set_state(CopyTradeState.setting_custom_min_amount)
        await callback.answer()
        return
    
    min_amount = float(callback.data.split("_")[-1])
    await state.update_data(min_amount=min_amount)
    await callback.answer(f"✅ Мин. сумма: ${min_amount}")
    
    await show_quick_setup_menu(callback.message, state)


@router.message(CopyTradeState.setting_custom_min_amount)
async def quick_custom_min_amount_input(message: types.Message, state: FSMContext):
    """Обработка кастомной минимальной суммы"""
    try:
        min_amount = float(message.text.strip().replace(',', '.'))
        
        if min_amount < 0.1 or min_amount > 1000:
            await message.answer(
                "⚠️ Сумма должна быть от $0.1 до $1000!\n"
                "Попробуйте снова:"
            )
            return
        
        try:
            await message.delete()
        except:
            pass
        
        await state.update_data(min_amount=min_amount)
        
        data = await state.get_data()
        await state.clear()
        for key, value in data.items():
            await state.update_data({key: value})
        
        await message.answer(f"✅ Минимальная сумма установлена: ${min_amount}\n\nВозвращаюсь к настройкам...")
        await show_quick_setup_menu_new_message(message, state)
        
    except ValueError:
        await message.answer("⚠️ Неверный формат! Введите число (например: 15 или 75.5)")


# ============== ПЕРВЫЕ СТАВКИ ==============

@router.callback_query(F.data == "quick_first_bet")
async def quick_first_bet(callback: CallbackQuery, state: FSMContext):
    """Переключение фильтра первых ставок"""
    data = await state.get_data()
    current = data.get("first_bet", False)
    new_value = not current
    
    await state.update_data(first_bet=new_value)
    
    text = "✅ Теперь копируются только первые ставки" if new_value else "❌ Копируются все ставки"
    await callback.answer(text)
    
    await show_quick_setup_menu(callback.message, state)


# ============== КОТИРОВКИ ==============

@router.callback_query(F.data == "quick_quotes")
async def quick_quotes(callback: CallbackQuery, state: FSMContext):
    """Выбор диапазона котировок"""
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Широкий (0.01 - 1.0)", callback_data="qq_0.01_1.0")],
            [InlineKeyboardButton(text="📊 Средний (0.1 - 0.9)", callback_data="qq_0.1_0.9")],
            [InlineKeyboardButton(text="📊 Узкий (0.2 - 0.8)", callback_data="qq_0.2_0.8")],
            [InlineKeyboardButton(text="📊 Безопасный (0.3 - 0.7)", callback_data="qq_0.3_0.7")],
            [InlineKeyboardButton(text="✏️ Настроить вручную", callback_data="qq_custom")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="quick_back")]
        ]
    )
    
    await callback.message.edit_text(
        "📊 **Выберите диапазон котировок:**\n\n"
        "• **Широкий** - копирует почти все ставки\n"
        "• **Средний** - исключает крайние значения\n"
        "• **Узкий** - только умеренные котировки\n"
        "• **Безопасный** - самые сбалансированные ставки",
        parse_mode="Markdown",
        reply_markup=kb
    )
    await callback.answer()


@router.callback_query(F.data.startswith("qq_"))
async def quick_quotes_selected(callback: CallbackQuery, state: FSMContext):
    """Сохранение диапазона котировок"""
    if callback.data == "qq_custom":
        await state.set_state(CopyTradeState.setting_min_quote)
        
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="0.01", callback_data="minquote_0.01"),
                    InlineKeyboardButton(text="0.05", callback_data="minquote_0.05"),
                    InlineKeyboardButton(text="0.10", callback_data="minquote_0.10")
                ],
                [
                    InlineKeyboardButton(text="0.20", callback_data="minquote_0.20"),
                    InlineKeyboardButton(text="0.30", callback_data="minquote_0.30"),
                    InlineKeyboardButton(text="0.40", callback_data="minquote_0.40")
                ],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="quick_back")]
            ]
        )
        
        await callback.message.edit_text(
            "📊 **Выберите минимальную котировку:**",
            parse_mode="Markdown",
            reply_markup=kb
        )
        await callback.answer()
        return
    
    quotes = callback.data.replace("qq_", "").split("_")
    min_quote = float(quotes[0])
    max_quote = float(quotes[1])
    
    await state.update_data(min_quote=min_quote, max_quote=max_quote)
    await callback.answer(f"✅ Котировки: {min_quote} - {max_quote}")
    
    await show_quick_setup_menu(callback.message, state)


# ============== МАРЖА ==============

@router.callback_query(F.data == "quick_margin")
async def quick_margin(callback: CallbackQuery, state: FSMContext):
    """Выбор маржи"""
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="$5", callback_data="qm_5"),
                InlineKeyboardButton(text="$10", callback_data="qm_10"),
                InlineKeyboardButton(text="$25", callback_data="qm_25")
            ],
            [
                InlineKeyboardButton(text="$50", callback_data="qm_50"),
                InlineKeyboardButton(text="$100", callback_data="qm_100"),
                InlineKeyboardButton(text="$250", callback_data="qm_250")
            ],
            [
                InlineKeyboardButton(text="$500", callback_data="qm_500"),
                InlineKeyboardButton(text="$1000", callback_data="qm_1000")
            ],
            [InlineKeyboardButton(text="✏️ Ввести свою сумму", callback_data="qm_custom")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="quick_back")]
        ]
    )
    
    await callback.message.edit_text(
        "💵 **Выберите размер маржи для каждой сделки:**\n"
        "(Эта сумма будет использоваться для копирования сделок)",
        parse_mode="Markdown",
        reply_markup=kb
    )
    await callback.answer()


@router.callback_query(F.data.startswith("qm_"))
async def quick_margin_selected(callback: CallbackQuery, state: FSMContext):
    """Сохранение маржи"""
    if callback.data == "qm_custom":
        await callback.message.edit_text(
            "✏️ **Ввод кастомной маржи**\n\n"
            "💰 Введите сумму в долларах (USD):\n\n"
            "Примеры: `15`, `75.5`, `333`\n\n"
            "⚠️ Минимум: $1\n"
            "⚠️ Максимум: $10000\n\n"
            "Отправьте число в чат:",
            parse_mode="Markdown",
            reply_markup=get_back_button("quick_back")
        )
        await state.set_state(CopyTradeState.setting_custom_margin)
        await callback.answer()
        return
    
    margin_amount = float(callback.data.split("_")[-1])
    await state.update_data(margin_amount=margin_amount)
    await callback.answer(f"✅ Маржа: ${margin_amount}")
    
    await show_quick_setup_menu(callback.message, state)


@router.message(CopyTradeState.setting_custom_margin)
async def quick_custom_margin_input(message: types.Message, state: FSMContext):
    """Обработка кастомной маржи"""
    try:
        margin_amount = float(message.text.strip().replace(',', '.'))
        
        if margin_amount < 1 or margin_amount > 10000:
            await message.answer(
                "⚠️ Сумма должна быть от $1 до $10000!\n"
                "Попробуйте снова:"
            )
            return
        
        try:
            await message.delete()
        except:
            pass
        
        await state.update_data(margin_amount=margin_amount)
        
        data = await state.get_data()
        await state.clear()
        for key, value in data.items():
            await state.update_data({key: value})
        
        await message.answer(f"✅ Маржа установлена: ${margin_amount}\n\nВозвращаюсь к настройкам...")
        await show_quick_setup_menu_new_message(message, state)
        
    except ValueError:
        await message.answer("⚠️ Неверный формат! Введите число (например: 15 или 75.5)")


async def show_quick_setup_menu_new_message(message, state: FSMContext):
    """Показывает меню быстрой настройки в новом сообщении"""
    data = await state.get_data()
    
    selected_wallet = data.get("selected_wallet")
    duration = data.get("duration", 3600)
    min_amount = data.get("min_amount", 5)
    first_bet = data.get("first_bet", False)
    min_quote = data.get("min_quote", 0.01)
    max_quote = data.get("max_quote", 1.0)
    margin_amount = data.get("margin_amount", 10)
    sl_percent = data.get("sl_percent", 30)
    tp_percent = data.get("tp_percent", 50)
    
    duration_text = f"{duration // 60} мин" if duration < 3600 else f"{duration // 3600} ч"
    first_bet_text = "✅ Да" if first_bet else "❌ Нет"
    
    wallet_text = "Не выбран"
    if selected_wallet:
        wallet_text = f"{selected_wallet[:6]}...{selected_wallet[-4:]}"
    
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"👛 Кошелек: {wallet_text}", callback_data="quick_select_wallet")],
            [InlineKeyboardButton(text=f"⏱ Длительность: {duration_text}", callback_data="quick_duration")],
            [InlineKeyboardButton(text=f"💰 Мин. сумма: ${min_amount}", callback_data="quick_min_amount")],
            [InlineKeyboardButton(text=f"🎯 Первые ставки: {first_bet_text}", callback_data="quick_first_bet")],
            [InlineKeyboardButton(text=f"📊 Котировки: {min_quote} - {max_quote}", callback_data="quick_quotes")],
            [InlineKeyboardButton(text=f"💵 Маржа: ${margin_amount}", callback_data="quick_margin")],
            [InlineKeyboardButton(text=f"🛑 SL (%): {sl_percent}%", callback_data="quick_sl")],
            [InlineKeyboardButton(text=f"🎯 TP (%): {tp_percent}%", callback_data="quick_tp")],
            [InlineKeyboardButton(text="🚀 Запустить мониторинг", callback_data="quick_start_monitoring")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="copy_trade_back")]
        ]
    )
    
    text = (
        "⚙️ **Быстрая настройка Copy-Trade**\n\n"
        "Нажмите на параметр, чтобы изменить его:\n\n"
        f"👛 **Кошелек:** {wallet_text}\n"
        f"⏱ **Длительность:** {duration_text}\n"
        f"💰 **Мин. сумма ставки:** ${min_amount}\n"
        f"🎯 **Только первые ставки:** {first_bet_text}\n"
        f"📊 **Диапазон котировок:** {min_quote} - {max_quote}\n"
        f"💵 **Маржа на сделку:** ${margin_amount}\n"
        f"🛑 **Stop Loss:** {sl_percent}%\n"
        f"🎯 **Take Profit:** {tp_percent}%\n\n"
        f"Когда всё готово - нажмите '🚀 Запустить мониторинг'"
    )
    
    await message.answer(text, parse_mode="Markdown", reply_markup=kb)


@router.callback_query(F.data == "quick_sl")
async def quick_sl_menu(callback: CallbackQuery, state: FSMContext):
    """Меню выбора Stop Loss"""
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="10%", callback_data="set_sl_10"),
                InlineKeyboardButton(text="20%", callback_data="set_sl_20"),
                InlineKeyboardButton(text="30%", callback_data="set_sl_30"),
            ],
            [
                InlineKeyboardButton(text="40%", callback_data="set_sl_40"),
                InlineKeyboardButton(text="50%", callback_data="set_sl_50"),
                InlineKeyboardButton(text="75%", callback_data="set_sl_75"),
            ],
            [
                InlineKeyboardButton(text="100%", callback_data="set_sl_100")
            ],
            [
                InlineKeyboardButton(text="⬅️ Назад", callback_data="quick_setup_back")
            ]
        ]
    )

    await callback.message.edit_text(
        "🛑 **Выберите Stop Loss (%)**",
        parse_mode="Markdown",
        reply_markup=kb
    )


@router.callback_query(F.data == "quick_tp")
async def quick_tp_menu(callback: CallbackQuery, state: FSMContext):
    """Меню выбора Take Profit"""
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="10%", callback_data="set_tp_10"),
                InlineKeyboardButton(text="20%", callback_data="set_tp_20"),
                InlineKeyboardButton(text="30%", callback_data="set_tp_30"),
            ],
            [
                InlineKeyboardButton(text="40%", callback_data="set_tp_40"),
                InlineKeyboardButton(text="50%", callback_data="set_tp_50"),
                InlineKeyboardButton(text="75%", callback_data="set_tp_75"),
            ],
            [
                InlineKeyboardButton(text="100%", callback_data="set_tp_100")
            ],
            [
                InlineKeyboardButton(text="⬅️ Назад", callback_data="quick_setup_back")
            ]
        ]
    )

    await callback.message.edit_text(
        "🎯 **Выберите Take Profit (%)**",
        parse_mode="Markdown",
        reply_markup=kb
    )


@router.callback_query(F.data.startswith("set_sl_"))
async def set_sl(callback: CallbackQuery, state: FSMContext):
    """Сохранение Stop Loss"""
    value = int(callback.data.split("_")[2])
    await state.update_data(sl_percent=value)
    await show_quick_setup_menu(callback.message, state)
    await callback.answer(f"✅ Stop Loss: {value}%")


@router.callback_query(F.data.startswith("set_tp_"))
async def set_tp(callback: CallbackQuery, state: FSMContext):
    """Сохранение Take Profit"""
    value = int(callback.data.split("_")[2])
    await state.update_data(tp_percent=value)
    await show_quick_setup_menu(callback.message, state)
    await callback.answer(f"✅ Take Profit: {value}%")


# ============== ЗАПУСК МОНИТОРИНГА ==============

@router.callback_query(F.data == "quick_start_monitoring")
async def quick_start_monitoring(callback: CallbackQuery, state: FSMContext):
    """Запуск мониторинга из быстрой настройки"""
    data = await state.get_data()
    
    if not data.get("selected_wallet"):
        await callback.answer("❌ Выберите кошелек!", show_alert=True)
        return
    
    await confirm_and_start_monitoring(callback, state)


@router.callback_query(F.data == "confirm_start_monitoring")
async def confirm_and_start_monitoring(callback: CallbackQuery, state: FSMContext):
    """Подтверждение и запуск мониторинга"""
    tg_id = callback.from_user.id
    data = await state.get_data()
    
    if tg_id in active_monitors and not active_monitors[tg_id].done():
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🛑 Остановить текущий", callback_data="stop_monitoring")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="copy_trade_back")]
            ]
        )
        await callback.message.edit_text(
            "⚠️ У вас уже запущен мониторинг!\n"
            "Сначала остановите текущий, чтобы запустить новый.",
            reply_markup=kb
        )
        await callback.answer()
        return
    
    private_key = await users_sql.get_private_key(tg_id)
    user_address = await users_sql.select_user_address(tg_id)
    api_key, api_secret, api_passphrase = await users_sql.get_api_credentials(tg_id)
    
    if not private_key:
        await callback.message.edit_text(
            "❌ Приватный ключ не найден!\n"
            "Используйте /start для повторной регистрации.",
            reply_markup=get_back_button("copy_trade_back")
        )
        await callback.answer()
        return
    
    if not all([api_key, api_secret, api_passphrase]):
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Продолжить без автоисполнения", callback_data="continue_without_api")],
                [InlineKeyboardButton(text="⬅️ Отмена", callback_data="copy_trade_back")]
            ]
        )
        await callback.message.edit_text(
            "⚠️ **API Credentials не настроены!**\n\n"
            "Без API credentials бот может только мониторить сделки,\n"
            "но не исполнять их автоматически.\n\n"
            "Вы получите уведомления о найденных сделках,\n"
            "но придется исполнять их вручную.\n\n"
            "Хотите продолжить в режиме \"только мониторинг\"?",
            parse_mode="Markdown",
            reply_markup=kb
        )
        await state.update_data(ready_to_start=True)
        await callback.answer()
        return
    
    await start_monitoring_task(callback, state, tg_id, data, private_key, user_address, api_key, api_secret, api_passphrase)


@router.callback_query(F.data == "continue_without_api")
async def continue_without_api(callback: CallbackQuery, state: FSMContext):
    """Продолжить мониторинг без API credentials"""
    tg_id = callback.from_user.id
    data = await state.get_data()
    
    private_key = await users_sql.get_private_key(tg_id)
    user_address = await users_sql.select_user_address(tg_id)
    
    await start_monitoring_task(callback, state, tg_id, data, private_key, user_address, None, None, None)


# ============== УПРАВЛЕНИЕ МОНИТОРИНГОМ ==============

@router.callback_query(F.data == "stop_monitoring")
async def stop_monitoring(callback: CallbackQuery, state: FSMContext):
    """Остановка мониторинга"""
    tg_id = callback.from_user.id
    
    if tg_id not in active_monitors:
        await callback.answer("❌ Нет активного мониторинга", show_alert=True)
        return
    
    task = active_monitors[tg_id]
    task.cancel()
    
    try:
        await task
    except asyncio.CancelledError:
        pass
    
    if tg_id in active_monitors:
        del active_monitors[tg_id]
    
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Запустить новый", callback_data="start_copy_trade")],
            [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="main_menu")]
        ]
    )
    
    await state.clear()
    await callback.message.edit_text(
        "🛑 **Мониторинг остановлен**\n\n"
        "Статистика была отправлена в чат.\n"
        "Вы можете запустить новый мониторинг в любое время.",
        parse_mode="Markdown",
        reply_markup=kb
    )
    await callback.answer("✅ Мониторинг остановлен")


@router.callback_query(F.data == "monitoring_stats")
async def show_monitoring_stats(callback: CallbackQuery):
    """Показать статистику текущего мониторинга"""
    tg_id = callback.from_user.id
    
    if tg_id not in active_monitors:
        await callback.answer("❌ Нет активного мониторинга", show_alert=True)
        return
    
    task = active_monitors[tg_id]
    
    if task.done():
        status = "Завершен"
    elif task.cancelled():
        status = "Отменен"
    else:
        status = "Активен ✅"
    
    await callback.answer(
        f"📊 Статус мониторинга: {status}\n"
        f"Вы получите детальную статистику после завершения.",
        show_alert=True
    )