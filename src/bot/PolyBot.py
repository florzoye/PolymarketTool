import asyncio
import logging
from itertools import islice

from aiogram import F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram import Bot, Dispatcher, types
from aiogram.types import BotCommand, CallbackQuery
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from db.users import UsersSQL
from db.manager import AsyncDatabaseManager
from src.bot.states import TrackSettings, RegisterState

from src.core.PolyScrapper import PolyScrapper
from utils.formatters import format_money, format_pnl
from data.config import BOT_TOKEN

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

db = AsyncDatabaseManager('users.db')
users_sql = UsersSQL(db)


async def set_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="copy_trade", description="Отслеживать и повторять новые сделки кошельков"),
    ]
    await bot.set_my_commands(commands)


def get_main_menu_keyboard():
    """Создает главное меню с inline кнопками"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='📊 Мои позиции', callback_data='show_positions')],
            [InlineKeyboardButton(text='🏆 Рейтинг', callback_data='show_leaderboard')],
            [InlineKeyboardButton(text='🔄 Сменить кошелек', callback_data='reset_wallet')],
            [InlineKeyboardButton(text='📋 Copy Trade', callback_data='copy_trade_menu')]
        ]
    )


# -----------------  COMMANDS -----------------
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    tg_id = message.from_user.id
    address = await users_sql.select_user_address(tg_id)

    if address is None:
        await message.answer(
            "👋 Привет! Твоего Polymarket адреса нет в базе.\n"
            "Пожалуйста, отправь его сюда:",
            parse_mode="Markdown"
        )
        await state.set_state(RegisterState.waiting_for_address)
    else:
        await message.answer(
            f"✅ Добро пожаловать!\n\n"
            f"Ваш адрес: `{address}`\n\n"
            f"Выберите действие:",
            parse_mode="Markdown",
            reply_markup=get_main_menu_keyboard()
        )


@dp.message(Command('copy_trade'))
async def cmd_copy_trade(message: types.Message):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='Кошельки на треке', callback_data='track_wallets')],
            [InlineKeyboardButton(text='Позиции кошельков на треке', callback_data='track_positions')],
            [InlineKeyboardButton(text='Запустить copy-trade для конкретных кошельков', callback_data='start_copy_trade')],
            [InlineKeyboardButton(text='⬅️ Главное меню', callback_data='main_menu')]
        ]
    )
    await message.answer('Меню copy-trade на Polymarket!', reply_markup=kb)


# ----------------- STATE -----------------
@dp.message(RegisterState.waiting_for_address)
async def get_address(message: types.Message, state: FSMContext):
    address = message.text.strip()
    tg_id = message.from_user.id

    if not address.startswith("0x") or len(address) != 42:
        await message.answer("⚠️ Это невалидный Ethereum/Polymarket адрес. Попробуй снова.")
        return

    await users_sql.add_user({
        "tg_id": tg_id,
        "address": address
    })

    await state.clear()
    await message.answer(
        f"✅ Адрес `{address}` сохранён.\n\n"
        f"Выберите действие:",
        parse_mode="Markdown",
        reply_markup=get_main_menu_keyboard()
    )


@dp.message(RegisterState.reset_address)
async def reset_address(message: types.Message, state: FSMContext):
    address = message.text.strip()
    tg_id = message.from_user.id

    if not address.startswith("0x") or len(address) != 42:
        await message.answer("⚠️ Это невалидный Ethereum/Polymarket адрес. Попробуй снова.")
        return

    await users_sql.update_user_address(
        tg_id=tg_id,
        new_address=address
    )

    await state.clear()
    await message.answer(
        f"✅ Адрес `{address}` сохранён.\n\n"
        f"Выберите действие:",
        parse_mode="Markdown",
        reply_markup=get_main_menu_keyboard()
    )


@dp.message(TrackSettings.waiting_for_new_wallet)
async def add_new_track_wallet_handler(message: types.Message, state: FSMContext):
    address = message.text.strip()
    tg_id = message.from_user.id

    if not address.startswith("0x") or len(address) != 42:
        await message.answer("⚠️ Это невалидный Ethereum/Polymarket адрес. Попробуй снова.")
        return

    await users_sql.add_track_wallet(tg_id, address)
    await state.clear()
    
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад к кошелькам", callback_data="track_wallets")]
        ]
    )
    
    await message.answer(
        f"✅ Кошелек `{address}` добавлен на трек!",
        parse_mode="Markdown",
        reply_markup=kb
    )


@dp.message(TrackSettings.waiting_for_delete_wallet)
async def delete_track_wallet_handler(message: types.Message, state: FSMContext):
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
    
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад к кошелькам", callback_data="track_wallets")]
        ]
    )
    
    await message.answer(
        f"✅ Кошелек `{address}` удален из трека!",
        parse_mode="Markdown",
        reply_markup=kb
    )


# ----------------- MAIN MENU CALLBACKS -----------------

@dp.callback_query(F.data == "main_menu")
async def show_main_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    tg_id = callback.from_user.id
    address = await users_sql.select_user_address(tg_id)
    
    if not address:
        await callback.message.edit_text(
            "❌ Адрес не найден. Используйте /start для регистрации."
        )
        await callback.answer()
        return
    
    await callback.message.edit_text(
        f"✅ Главное меню\n"
        f"Ваш адрес: `{address}`\n\n"
        f"Выберите действие:",
        parse_mode="Markdown",
        reply_markup=get_main_menu_keyboard()
    )
    await callback.answer()


@dp.callback_query(F.data == "show_positions")
async def show_positions(callback: CallbackQuery):
    tg_id = callback.from_user.id
    address = await users_sql.select_user_address(tg_id)

    if not address:
        await callback.answer("❌ Адрес не найден. Сначала введите его через /start.", show_alert=True)
        return

    await callback.answer("⏳ Получаю данные с Polymarket...")

    scrapper = PolyScrapper(address)
    positions = await scrapper.get_account_positions()

    if not positions:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="main_menu")]
            ]
        )
        await callback.message.edit_text(
            "😕 Похоже, у тебя нет активных позиций на Polymarket.",
            reply_markup=kb
        )
        return

    max_show = 10
    positions = positions[:max_show]

    text = f"📊 Топ {len(positions)} позиций по адресу `{address}`:\n\n"

    for i, pos in enumerate(positions, 1):
        title = pos.get("title", "Без названия")
        current = round(float(pos.get("currentValue", 0)), 2)
        pnl = round(float(pos.get("cashPnl", 0)), 2)
        percent = round(float(pos.get("percentRealizedPnl", 0) or 0), 2)

        text += (
            f"**{i}. {title}**\n"
            f"💰 Текущая стоимость: `${current}`\n"
            f"📈 PnL: `${pnl}` ({percent}%)\n"
            f"───────────────────────\n"
        )
    
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="show_positions")],
            [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="main_menu")]
        ]
    )
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)


@dp.callback_query(F.data == "show_leaderboard")
async def show_leaderboard(callback: CallbackQuery):
    tg_id = callback.from_user.id
    address = await users_sql.select_user_address(tg_id)

    if not address:
        await callback.answer("❌ Адрес не найден. Сначала введите его через /start.", show_alert=True)
        return
    
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='Дневной', callback_data='day_lead')],
            [InlineKeyboardButton(text='Недельный', callback_data='week_lead')],
            [InlineKeyboardButton(text='⬅️ Главное меню', callback_data='main_menu')]
        ]
    )
    
    await callback.answer("⏳ Загружаю данные...")
    
    scrapper = PolyScrapper(address)
    lead = await scrapper.check_leaderboard()

    userName = lead.get('userName', 'Unknown')
    rank = lead.get('rank', '—')
    vol = lead.get('vol', 0)
    pnl = lead.get('pnl', 0)

    text = (
        f"**Данные по вашему аккаунту - {userName}**\n"
        f"🏆 Место в топе: {rank}\n"
        f"👛 Обьем за все время: {round(vol, 3)}\n"
        f"💸 Реализованный PnL за все время: {round(pnl, 3)}\n"
        f"**Обновить информацию за конкретный период?**"
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)


@dp.callback_query(F.data == "reset_wallet")
async def reset_wallet(callback: CallbackQuery, state: FSMContext):
    tg_id = callback.from_user.id
    address = await users_sql.select_user_address(tg_id)
    
    if not address:
        await callback.answer("❌ Адрес не найден. Сначала введите его через /start.", show_alert=True)
        return
    
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data="main_menu")]
        ]
    )
    
    await callback.message.edit_text(
        f'Сейчас ваш адресс - `{address}`\n\n'
        f'Если желаете поменять, пришлите новый в чат.',
        parse_mode="Markdown",
        reply_markup=kb
    )
    await state.set_state(RegisterState.reset_address)
    await callback.answer()


@dp.callback_query(F.data == "copy_trade_menu")
async def copy_trade_menu(callback: CallbackQuery):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='Кошельки на треке', callback_data='track_wallets')],
            [InlineKeyboardButton(text='Позиции кошельков на треке', callback_data='track_positions')],
            [InlineKeyboardButton(text='Запустить copy-trade для конкретных кошельков', callback_data='start_copy_trade')],
            [InlineKeyboardButton(text='⬅️ Главное меню', callback_data='main_menu')]
        ]
    )
    await callback.message.edit_text('Меню copy-trade на Polymarket!', reply_markup=kb)
    await callback.answer()


# ----------------- LEADERBOARD CALLBACKS -----------------

@dp.callback_query(F.data == "week_lead")
async def check_week_lead(callback: CallbackQuery):
    tg_id = callback.from_user.id
    address = await users_sql.select_user_address(tg_id)

    if not address:
        await callback.answer("❌ Адрес не найден. Сначала введите его через /start.", show_alert=True)
        return
    
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='Дневной', callback_data='day_lead')],
            [InlineKeyboardButton(text='Недельный', callback_data='week_lead')],
            [InlineKeyboardButton(text='⬅️ Главное меню', callback_data='main_menu')]
        ]
    )
    
    await callback.answer("⏳ Загружаю данные...")
    
    scrapper = PolyScrapper(address)
    lead = await scrapper.check_leaderboard(timePeriod='week')

    userName = lead.get('userName', 'Unknown')
    rank = lead.get('rank', '—')
    vol = lead.get('vol', 0)
    pnl = lead.get('pnl', 0)

    text = (
        f"**Данные по вашему аккаунту - {userName}**\n"
        f"🏆 Место в топе: {rank}\n"
        f"👛 Обьем за эту неделю: {round(vol, 3)}\n"
        f"💸 Реализованный PnL за эту неделю: {round(pnl, 3)}\n"
        f"**Обновить информацию за конкретный период?**"
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)


@dp.callback_query(F.data == "day_lead")
async def check_day_lead(callback: CallbackQuery):
    tg_id = callback.from_user.id
    address = await users_sql.select_user_address(tg_id)

    if not address:
        await callback.answer("❌ Адрес не найден. Сначала введите его через /start.", show_alert=True)
        return
    
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='Дневной', callback_data='day_lead')],
            [InlineKeyboardButton(text='Недельный', callback_data='week_lead')],
            [InlineKeyboardButton(text='⬅️ Главное меню', callback_data='main_menu')]
        ]
    )
    
    await callback.answer("⏳ Загружаю данные...")
    
    scrapper = PolyScrapper(address)
    lead = await scrapper.check_leaderboard(timePeriod='day')

    userName = lead.get('userName', 'Unknown')
    rank = lead.get('rank', '—')
    vol = lead.get('vol', 0)
    pnl = lead.get('pnl', 0)

    text = (
        f"**Данные по вашему аккаунту - {userName}**\n"
        f"🏆 Место в топе: {rank}\n"
        f"👛 Обьем за сегодня: {round(vol, 3)}\n"
        f"💸 Реализованный PnL за сегодня: {round(pnl, 3)}\n"
        f"**Обновить информацию за конкретный период?**"
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)


# ----------------- COPY TRADE CALLBACKS -----------------

@dp.callback_query(F.data == "change_count")
async def change_count(callback: CallbackQuery, state: FSMContext):
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


@dp.callback_query(F.data.startswith("set_count_"))
async def set_count(callback: CallbackQuery, state: FSMContext):
    count = int(callback.data.split("_")[-1])
    await state.update_data(count=count)
    await show_track_settings_menu(callback.message, state)
    await callback.answer(f"✅ Количество установлено: {count}")


@dp.callback_query(F.data == "change_min_value")
async def change_min_value(callback: CallbackQuery, state: FSMContext):
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


@dp.callback_query(F.data.startswith("set_value_"))
async def set_min_value(callback: CallbackQuery, state: FSMContext):
    value = float(callback.data.split("_")[-1])
    await state.update_data(min_value=value)
    await show_track_settings_menu(callback.message, state)
    await callback.answer(f"✅ Минимальный value установлен: ${value}")


@dp.callback_query(F.data == "change_sort")
async def change_sort(callback: CallbackQuery, state: FSMContext):
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


@dp.callback_query(F.data.startswith("set_sort_"))
async def set_sort(callback: CallbackQuery, state: FSMContext):
    sort_by = callback.data.replace("set_sort_", "")
    await state.update_data(sort_by=sort_by)
    
    sort_names = {
        'CASHPNL': 'По PnL',
        'INITIAL': 'Новые позиции',
        'CURRENT': 'По текущей стоимости'
    }
    
    await show_track_settings_menu(callback.message, state)
    await callback.answer(f"✅ Сортировка: {sort_names.get(sort_by, sort_by)}")


@dp.callback_query(F.data == "back_to_track_settings")
async def back_to_track_settings(callback: CallbackQuery, state: FSMContext):
    await show_track_settings_menu(callback.message, state)
    await callback.answer()


@dp.callback_query(F.data == "show_track_positions")
async def show_track_positions(callback: CallbackQuery, state: FSMContext):
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


@dp.callback_query(F.data == "track_wallets")
async def wallets_in_track(callback: CallbackQuery):
    tg_id = callback.from_user.id
    track_addresses = await users_sql.get_track_wallets(tg_id)

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='Добавить новый кошелек', callback_data='add_new_track_wallet')],
            [InlineKeyboardButton(text='Удалить кошелек на треке', callback_data='delete_track_wallet')],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="copy_trade_back")]
        ]
    )

    if not track_addresses:
        await callback.message.edit_text(
            "К вашему аккаунту не привязаны кошельки для трейкинга.\n"
            "Привяжите их и запустите заново.",
            reply_markup=kb
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

    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)


@dp.callback_query(F.data == "add_new_track_wallet")
async def add_new_track_wallet(callback: CallbackQuery, state: FSMContext):
    back_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="track_wallets")]
        ]
    )
    
    await callback.message.edit_text(
        "Отправьте адрес кошелька, который хотите добавить на трек:\n"
        "(формат: 0x...)",
        reply_markup=back_kb
    )
    await state.set_state(TrackSettings.waiting_for_new_wallet)
    await callback.answer()


@dp.callback_query(F.data == "delete_track_wallet")
async def delete_track_wallet(callback: CallbackQuery, state: FSMContext):
    tg_id = callback.from_user.id
    track_wallets = await users_sql.get_track_wallets(tg_id)
    
    back_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="track_wallets")]
        ]
    )
    
    if not track_wallets:
        await callback.message.edit_text(
            "У вас нет кошельков на треке для удаления.",
            reply_markup=back_kb
        )
        await callback.answer()
        return
    
    wallet_list = "\n".join([f"`{w}`" for w in track_wallets])
    
    await callback.message.edit_text(
        f"Ваши кошельки на треке:\n\n{wallet_list}\n\n"
        "Отправьте адрес кошелька, который хотите удалить:",
        parse_mode="Markdown",
        reply_markup=back_kb
    )
    await state.set_state(TrackSettings.waiting_for_delete_wallet)
    await callback.answer()


@dp.callback_query(F.data == "track_positions")
async def positions_wallets(callback: CallbackQuery, state: FSMContext):
    tg_id = callback.from_user.id
    track_addresses = await users_sql.get_track_wallets(tg_id)

    back_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="copy_trade_back")]
        ]
    )

    if not track_addresses:
        await callback.message.edit_text(
            "К вашему аккаунту не привязаны кошельки для трейкинга.\n"
            "Привяжите их и запустите заново.",
            reply_markup=back_kb
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

@dp.callback_query(F.data == "copy_trade_back")
async def copy_trade_back(callback: CallbackQuery, state: FSMContext):
    await state.clear()

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='Кошельки на треке', callback_data='track_wallets')],
            [InlineKeyboardButton(text='Позиции кошельков на треке', callback_data='track_positions')],
            [InlineKeyboardButton(text='Запустить copy-trade для конкретных кошельков', callback_data='start_copy_trade')],
            [InlineKeyboardButton(text='⬅️ Главное меню', callback_data='main_menu')]
        ]
    )

    await callback.message.edit_text("Меню copy-trade на Polymarket!", reply_markup=kb)
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


async def main():
    try:
        await users_sql.create_tables()
        await set_commands(bot)
        await dp.start_polling(bot)
    except Exception as e:
        logging.exception("Fatal error in bot:")
    finally:
        await bot.session.close()
        # await users_sql.clear_users()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())