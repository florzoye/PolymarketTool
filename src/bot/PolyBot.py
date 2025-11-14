import time
import asyncio
import logging
from typing import Dict
from itertools import islice

from aiogram import F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram import Bot, Dispatcher, types
from aiogram.types import BotCommand, CallbackQuery
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from db.users import UsersSQL
from db.manager import AsyncDatabaseManager
from src.bot.states import TrackSettings, RegisterState, CopyTradeState

from src.core.PolyCopy import PolyCopy
from src.models.settings import Settings
from src.models.position import Position
from src.core.PolyScrapper import PolyScrapper
from utils.formatters import format_money, format_pnl

from data.config import BOT_TOKEN

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

db = AsyncDatabaseManager('data/users.db')
users_sql = UsersSQL(db)

active_monitors: Dict[int, asyncio.Task] = {}


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
            "👋 Привет! Добро пожаловать в Polymarket Copy Trading Bot!\n\n"
            "Для начала работы мне нужен ваш адрес на Polymarket.\n"
            "📝 Отправьте ваш адрес (формат: 0x...):",
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

    await state.update_data(address=address)
    
    await message.answer(
        "✅ Адрес принят!\n\n"
        "🔐 Теперь отправьте ваш приватный ключ для автоматического исполнения сделок.\n\n"
        "⚠️ **ВАЖНО**: Ваш приватный ключ будет надежно храниться в зашифрованном виде.\n"
        "Он нужен для автоматического копирования сделок.\n\n"
        "Формат: 0x... (64 символа после 0x)",
        parse_mode="Markdown"
    )
    await state.set_state(RegisterState.waiting_for_private_key)


@dp.message(RegisterState.waiting_for_private_key)
async def get_private_key(message: types.Message, state: FSMContext):
    private_key = message.text.strip()
    
    try:
        await message.delete()
    except:
        pass

    if not private_key.startswith("0x") or len(private_key) != 66:
        await message.answer(
            "⚠️ Невалидный приватный ключ.\n"
            "Формат должен быть: 0x... (66 символов)\n\n"
            "Попробуйте снова:"
        )
        return

    await state.update_data(private_key=private_key)
    
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, хочу", callback_data="setup_api_yes")],
            [InlineKeyboardButton(text="❌ Пропустить (ограниченный функционал)", callback_data="setup_api_no")]
        ]
    )
    
    await message.answer(
        "✅ Приватный ключ принят!\n\n"
        "🔐 **API Credentials (опционально)**\n\n"
        "Для автоматического исполнения ордеров через Polymarket API нужны:\n"
        "• API Key\n"
        "• API Secret\n"
        "• API Passphrase\n\n"
        "📖 Как получить: зайдите на  https://polymarket.com, зайдите настройки -> builder -> add API\n\n"
        "⚠️ **Без API credentials** бот сможет только мониторить сделки, но не исполнять их автоматически.\n\n"
        "Хотите настроить API credentials сейчас?",
        parse_mode="Markdown",
        reply_markup=kb
    )
    await state.set_state(RegisterState.waiting_for_api_key)


@dp.callback_query(F.data == "setup_api_yes")
async def setup_api_yes(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🔑 **Шаг 1/3: API Key**\n\n"
        "Отправьте ваш Polymarket API Key:\n"
        "(Получить можно на https://polymarket.com/settings/api)\n\n"
        "Формат: строка из букв и цифр",
        parse_mode="Markdown"
    )
    await state.set_state(RegisterState.waiting_for_api_key)
    await callback.answer()


@dp.callback_query(F.data == "setup_api_no")
async def setup_api_no(callback: CallbackQuery, state: FSMContext):
    tg_id = callback.from_user.id
    data = await state.get_data()
    
    address = data.get("address")
    private_key = data.get("private_key")
    
    await users_sql.add_user({
        "tg_id": tg_id,
        "address": address
    })
    await users_sql.update_private_key(tg_id, private_key)
    
    await state.clear()
    await callback.message.edit_text(
        f"✅ Регистрация завершена!\n\n"
        f"📍 Адрес: `{address}`\n"
        f"🔐 Приватный ключ: сохранен\n"
        f"⚠️ API Credentials: не настроены\n\n"
        f"⚠️ **Внимание:** Без API credentials бот будет работать в режиме \"только мониторинг\".\n"
        f"Автоматическое исполнение сделок будет недоступно.\n\n"
        f"Вы можете добавить API credentials позже через настройки.",
        parse_mode="Markdown",
        reply_markup=get_main_menu_keyboard()
    )
    await callback.answer()


@dp.message(RegisterState.waiting_for_api_key)
async def get_api_key(message: types.Message, state: FSMContext):
    api_key = message.text.strip()
    
    try:
        await message.delete()
    except:
        pass
    
    if len(api_key) < 10:
        await message.answer("⚠️ API Key слишком короткий. Попробуйте снова:")
        return
    
    await state.update_data(api_key=api_key)
    
    await message.answer(
        "✅ API Key принят!\n\n"
        "🔑 **Шаг 2/3: API Secret**\n\n"
        "Теперь отправьте ваш API Secret:",
        parse_mode="Markdown"
    )
    await state.set_state(RegisterState.waiting_for_api_secret)


@dp.message(RegisterState.waiting_for_api_secret)
async def get_api_secret(message: types.Message, state: FSMContext):
    api_secret = message.text.strip()
    
    try:
        await message.delete()
    except:
        pass
    
    if len(api_secret) < 10:
        await message.answer("⚠️ API Secret слишком короткий. Попробуйте снова:")
        return
    
    await state.update_data(api_secret=api_secret)
    
    await message.answer(
        "✅ API Secret принят!\n\n"
        "🔑 **Шаг 3/3: API Passphrase**\n\n"
        "Наконец, отправьте ваш API Passphrase:",
        parse_mode="Markdown"
    )
    await state.set_state(RegisterState.waiting_for_api_passphrase)


@dp.message(RegisterState.waiting_for_api_passphrase)
async def get_api_passphrase(message: types.Message, state: FSMContext):
    api_passphrase = message.text.strip()
    tg_id = message.from_user.id
    
    try:
        await message.delete()
    except:
        pass
    
    if len(api_passphrase) < 3:
        await message.answer("⚠️ API Passphrase слишком короткий. Попробуйте снова:")
        return
    
    # Получаем все данные
    data = await state.get_data()
    address = data.get("address")
    private_key = data.get("private_key")
    api_key = data.get("api_key")
    api_secret = data.get("api_secret")
    
    await users_sql.add_user({
        "tg_id": tg_id,
        "address": address
    })
    await users_sql.update_private_key(tg_id, private_key)
    await users_sql.update_api_credentials(tg_id, api_key, api_secret, api_passphrase)
    
    await state.clear()
    
    await message.answer(
        f"✅ **Регистрация полностью завершена!**\n\n"
        f"📍 Адрес: `{address}`\n"
        f"🔐 Приватный ключ: сохранен\n"
        f"🔑 API Credentials: настроены ✅\n\n"
        f"🎉 Теперь бот может автоматически исполнять сделки!\n"
        f"Все данные надежно зашифрованы.",
        parse_mode="Markdown",
        reply_markup=get_main_menu_keyboard()
    )

@dp.message(RegisterState.reset_address)
async def reset_address(message: types.Message, state: FSMContext):
    address = message.text.strip()

    if not address.startswith("0x") or len(address) != 42:
        await message.answer("⚠️ Это невалидный Ethereum/Polymarket адрес. Попробуй снова.")
        return

    await state.update_data(new_address=address)
    
    await message.answer(
        "✅ Новый адрес принят!\n\n"
        "🔐 Отправьте новый приватный ключ для этого адреса:",
        parse_mode="Markdown"
    )
    await state.set_state(RegisterState.reset_private_key)


@dp.message(RegisterState.reset_private_key)
async def reset_private_key(message: types.Message, state: FSMContext):
    private_key = message.text.strip()
    tg_id = message.from_user.id
    
    try:
        await message.delete()
    except:
        pass

    if not private_key.startswith("0x") or len(private_key) != 66:
        await message.answer("⚠️ Невалидный приватный ключ. Попробуйте снова.")
        return

    data = await state.get_data()
    new_address = data.get("new_address")

    await users_sql.update_user_address(tg_id, new_address)
    await users_sql.update_private_key(tg_id, private_key)

    await state.clear()
    await message.answer(
        f"✅ Данные обновлены!\n\n"
        f"📍 Новый адрес: `{new_address}`\n"
        f"🔐 Приватный ключ обновлен\n\n"
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


# ============== COPY TRADE START FLOW ==============

@dp.callback_query(F.data == "start_copy_trade")
async def start_copy_trade_flow(callback: CallbackQuery, state: FSMContext):
    """Начало процесса настройки copy-trade"""
    tg_id = callback.from_user.id
    track_addresses = await users_sql.get_track_wallets(tg_id)
    
    if not track_addresses:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="copy_trade_back")]
            ]
        )
        await callback.message.edit_text(
            "❌ У вас нет кошельков на треке.\n"
            "Сначала добавьте кошельки через меню 'Кошельки на треке'.",
            reply_markup=kb
        )
        await callback.answer()
        return
    
    keyboard = []
    for i, address in enumerate(track_addresses):
        scrapper = PolyScrapper(address)
        lead_data = await scrapper.check_leaderboard()
        name = lead_data.get('userName', 'Unknown') if isinstance(lead_data, dict) else 'Unknown'
        
        keyboard.append([InlineKeyboardButton(
            text=f"{name} ({address[:6]}...{address[-4:]})",
            callback_data=f"select_wallet_{i}"
        )])
    
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="copy_trade_back")])
    
    kb = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    # Сохраняем список адресов в состояние
    await state.update_data(track_addresses=track_addresses)
    await state.set_state(CopyTradeState.selecting_wallet)
    
    await callback.message.edit_text(
        "👛 **Выберите кошелек для мониторинга:**\n\n"
        "Выберите кошелек, сделки которого вы хотите копировать.",
        parse_mode="Markdown",
        reply_markup=kb
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("select_wallet_"))
async def wallet_selected(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора кошелька"""
    wallet_index = int(callback.data.split("_")[-1])
    data = await state.get_data()
    track_addresses = data.get("track_addresses", [])
    
    if wallet_index >= len(track_addresses):
        await callback.answer("❌ Ошибка выбора кошелька", show_alert=True)
        return
    
    selected_wallet = track_addresses[wallet_index]
    await state.update_data(selected_wallet=selected_wallet)
    
    # Переходим к выбору длительности
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="5 мин", callback_data="duration_300"),
                InlineKeyboardButton(text="15 мин", callback_data="duration_900")
            ],
            [
                InlineKeyboardButton(text="30 мин", callback_data="duration_1800"),
                InlineKeyboardButton(text="1 час", callback_data="duration_3600")
            ],
            [
                InlineKeyboardButton(text="2 часа", callback_data="duration_7200"),
                InlineKeyboardButton(text="6 часов", callback_data="duration_21600")
            ],
            [
                InlineKeyboardButton(text="12 часов", callback_data="duration_43200"),
                InlineKeyboardButton(text="24 часа", callback_data="duration_86400")
            ],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="start_copy_trade")]
        ]
    )
    
    await state.set_state(CopyTradeState.setting_duration)
    
    await callback.message.edit_text(
        f"✅ Выбран кошелек: `{selected_wallet}`\n\n"
        f"⏱ **Выберите длительность мониторинга:**",
        parse_mode="Markdown",
        reply_markup=kb
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("duration_"))
async def duration_selected(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора длительности"""
    duration = int(callback.data.split("_")[-1])
    await state.update_data(duration=duration)
    
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="$1", callback_data="minamount_1"),
                InlineKeyboardButton(text="$5", callback_data="minamount_5"),
                InlineKeyboardButton(text="$10", callback_data="minamount_10")
            ],
            [
                InlineKeyboardButton(text="$25", callback_data="minamount_25"),
                InlineKeyboardButton(text="$50", callback_data="minamount_50"),
                InlineKeyboardButton(text="$100", callback_data="minamount_100")
            ],
            [
                InlineKeyboardButton(text="$250", callback_data="minamount_250"),
                InlineKeyboardButton(text="$500", callback_data="minamount_500")
            ],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_wallet_select")]
        ]
    )
    
    await state.set_state(CopyTradeState.setting_min_amount)
    
    duration_text = f"{duration // 60} мин" if duration < 3600 else f"{duration // 3600} ч"
    
    await callback.message.edit_text(
        f"⏱ Длительность: **{duration_text}**\n\n"
        f"💰 **Выберите минимальную сумму ставки:**",
        parse_mode="Markdown",
        reply_markup=kb
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("minamount_"))
async def min_amount_selected(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора минимальной суммы"""
    min_amount = float(callback.data.split("_")[-1])
    await state.update_data(min_amount=min_amount)
    
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да", callback_data="firstbet_true"),
                InlineKeyboardButton(text="❌ Нет", callback_data="firstbet_false")
            ],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_duration")]
        ]
    )
    
    await state.set_state(CopyTradeState.setting_first_bet)
    
    await callback.message.edit_text(
        f"💰 Минимальная сумма: **${min_amount}**\n\n"
        f"🎯 **Копировать только первые ставки на рынок?**\n"
        f"(Если да, то будут копироваться только ставки, которые являются первыми на конкретный рынок)",
        parse_mode="Markdown",
        reply_markup=kb
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("firstbet_"))
async def first_bet_selected(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора фильтра первой ставки"""
    first_bet = callback.data.split("_")[-1] == "true"
    await state.update_data(first_bet=first_bet)
    
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
            [
                InlineKeyboardButton(text="0.50", callback_data="minquote_0.50"),
                InlineKeyboardButton(text="0.60", callback_data="minquote_0.60")
            ],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_minamount")]
        ]
    )
    
    await state.set_state(CopyTradeState.setting_min_quote)
    
    first_bet_text = "✅ Да" if first_bet else "❌ Нет"
    
    await callback.message.edit_text(
        f"🎯 Только первые ставки: **{first_bet_text}**\n\n"
        f"📊 **Выберите минимальную котировку:**\n"
        f"(Ставки с котировкой ниже этого значения будут игнорироваться)",
        parse_mode="Markdown",
        reply_markup=kb
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("minquote_"))
async def min_quote_selected(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора минимальной котировки"""
    min_quote = float(callback.data.split("_")[-1])
    await state.update_data(min_quote=min_quote)
    
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="0.50", callback_data="maxquote_0.50"),
                InlineKeyboardButton(text="0.60", callback_data="maxquote_0.60"),
                InlineKeyboardButton(text="0.70", callback_data="maxquote_0.70")
            ],
            [
                InlineKeyboardButton(text="0.80", callback_data="maxquote_0.80"),
                InlineKeyboardButton(text="0.90", callback_data="maxquote_0.90"),
                InlineKeyboardButton(text="0.95", callback_data="maxquote_0.95")
            ],
            [
                InlineKeyboardButton(text="0.99", callback_data="maxquote_0.99"),
                InlineKeyboardButton(text="1.00", callback_data="maxquote_1.00")
            ],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_firstbet")]
        ]
    )
    
    await state.set_state(CopyTradeState.setting_max_quote)
    
    await callback.message.edit_text(
        f"📊 Минимальная котировка: **{min_quote}**\n\n"
        f"📈 **Выберите максимальную котировку:**\n"
        f"(Ставки с котировкой выше этого значения будут игнорироваться)",
        parse_mode="Markdown",
        reply_markup=kb
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("maxquote_"))
async def max_quote_selected(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора максимальной котировки и переход к настройке маржи"""
    max_quote = float(callback.data.split("_")[-1])
    await state.update_data(max_quote=max_quote)
    
    # Переходим к настройке маржи
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="$5", callback_data="margin_5"),
                InlineKeyboardButton(text="$10", callback_data="margin_10"),
                InlineKeyboardButton(text="$25", callback_data="margin_25")
            ],
            [
                InlineKeyboardButton(text="$50", callback_data="margin_50"),
                InlineKeyboardButton(text="$100", callback_data="margin_100"),
                InlineKeyboardButton(text="$250", callback_data="margin_250")
            ],
            [
                InlineKeyboardButton(text="$500", callback_data="margin_500"),
                InlineKeyboardButton(text="$1000", callback_data="margin_1000")
            ],
            [InlineKeyboardButton(text="✏️ Ввести свою сумму", callback_data="margin_custom")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_minquote")]
        ]
    )
    
    await state.set_state(CopyTradeState.setting_margin)
    
    await callback.message.edit_text(
        f"📈 Максимальная котировка: **{max_quote}**\n\n"
        f"💰 **Выберите размер маржи для каждой сделки:**\n"
        f"(Эта сумма будет использоваться для копирования сделок)\n\n"
        f"💡 Вы также можете ввести свою сумму",
        parse_mode="Markdown",
        reply_markup=kb
    )
    await callback.answer()


@dp.callback_query(F.data == "margin_custom")
async def margin_custom_prompt(callback: CallbackQuery, state: FSMContext):
    """Запрос на ввод кастомной маржи"""
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад к выбору", callback_data="back_to_margin_select")]
        ]
    )
    
    await callback.message.edit_text(
        "✏️ **Ввод кастомной маржи**\n\n"
        "💰 Введите сумму в долларах (USD):\n\n"
        "Примеры:\n"
        "• `15` - пятнадцать долларов\n"
        "• `75.5` - семьдесят пять долларов и 50 центов\n"
        "• `333` - триста тридцать три доллара\n\n"
        "⚠️ **Минимум:** $1\n"
        "⚠️ **Максимум:** $10000\n\n"
        "Отправьте число в чат:",
        parse_mode="Markdown",
        reply_markup=kb
    )
    await state.set_state(CopyTradeState.setting_custom_margin)
    await callback.answer()


@dp.message(CopyTradeState.setting_custom_margin)
async def custom_margin_input(message: types.Message, state: FSMContext):
    """Обработка введенной кастомной маржи"""
    try:
        margin_amount = float(message.text.strip().replace(',', '.'))
        
        if margin_amount < 1:
            await message.answer(
                "⚠️ Сумма слишком маленькая!\n"
                "Минимальная маржа: $1\n\n"
                "Попробуйте снова:"
            )
            return
        
        if margin_amount > 10000:
            await message.answer(
                "⚠️ Сумма слишком большая!\n"
                "Максимальная маржа: $10000\n\n"
                "Попробуйте снова:"
            )
            return
        
        try:
            await message.delete()
        except:
            pass
        
        await state.update_data(margin_amount=margin_amount)
        
        data = await state.get_data()
        
        selected_wallet = data.get("selected_wallet", "")
        duration = data.get("duration", 0)
        min_amount = data.get("min_amount", 0)
        first_bet = data.get("first_bet", False)
        min_quote = data.get("min_quote", 0)
        max_quote = data.get("max_quote", 1)
        
        duration_text = f"{duration // 60} мин" if duration < 3600 else f"{duration // 3600} ч"
        first_bet_text = "✅ Да" if first_bet else "❌ Нет"
        
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🚀 Запустить мониторинг", callback_data="confirm_start_monitoring")],
                [InlineKeyboardButton(text="🔄 Изменить настройки", callback_data="start_copy_trade")],
                [InlineKeyboardButton(text="⬅️ Отмена", callback_data="copy_trade_back")]
            ]
        )
        
        await state.set_state(CopyTradeState.confirming_settings)
        
        text = (
            "📋 **Итоговые настройки мониторинга:**\n\n"
            f"👛 Кошелек: `{selected_wallet[:8]}...{selected_wallet[-6:]}`\n"
            f"⏱ Длительность: **{duration_text}**\n"
            f"💰 Мин. сумма: **${min_amount}**\n"
            f"🎯 Только первые ставки: **{first_bet_text}**\n"
            f"📊 Котировки: **{min_quote} - {max_quote}**\n"
            f"💵 Маржа на сделку: **${margin_amount}** ✏️\n\n"
            f"⚠️ При нахождении подходящей сделки, она будет автоматически исполнена!\n\n"
            f"Всё верно? Нажмите '🚀 Запустить мониторинг'"
        )
        
        await message.answer(text, parse_mode="Markdown", reply_markup=kb)
        
    except ValueError:
        await message.answer(
            "⚠️ Неверный формат!\n\n"
            "Введите число (например: 15 или 75.5)\n"
            "Попробуйте снова:"
        )


@dp.callback_query(F.data == "back_to_margin_select")
async def back_to_margin_select(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору предустановленной маржи"""
    data = await state.get_data()
    max_quote = data.get("max_quote", 0.99)
    
    # Эмулируем выбор max_quote заново
    fake_data = f"maxquote_{max_quote}"
    callback.data = fake_data
    await max_quote_selected(callback, state)


@dp.callback_query(F.data.startswith("margin_"))
async def margin_selected(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора размера маржи и показ итоговой настройки"""
    if callback.data == "margin_custom":
        return
    
    margin_amount = float(callback.data.split("_")[-1])
    await state.update_data(margin_amount=margin_amount)
    
    data = await state.get_data()
    
    selected_wallet = data.get("selected_wallet", "")
    duration = data.get("duration", 0)
    min_amount = data.get("min_amount", 0)
    first_bet = data.get("first_bet", False)
    min_quote = data.get("min_quote", 0)
    max_quote = data.get("max_quote", 1)
    
    duration_text = f"{duration // 60} мин" if duration < 3600 else f"{duration // 3600} ч"
    first_bet_text = "✅ Да" if first_bet else "❌ Нет"
    
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Запустить мониторинг", callback_data="confirm_start_monitoring")],
            [InlineKeyboardButton(text="🔄 Изменить настройки", callback_data="start_copy_trade")],
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data="copy_trade_back")]
        ]
    )
    
    await state.set_state(CopyTradeState.confirming_settings)
    
    text = (
        "📋 **Итоговые настройки мониторинга:**\n\n"
        f"👛 Кошелек: `{selected_wallet[:8]}...{selected_wallet[-6:]}`\n"
        f"⏱ Длительность: **{duration_text}**\n"
        f"💰 Мин. сумма: **${min_amount}**\n"
        f"🎯 Только первые ставки: **{first_bet_text}**\n"
        f"📊 Котировки: **{min_quote} - {max_quote}**\n"
        f"💵 Маржа на сделку: **${margin_amount}**\n\n"
        f"⚠️ При нахождении подходящей сделки, она будет автоматически исполнена!\n\n"
        f"Всё верно? Нажмите '🚀 Запустить мониторинг'"
    )
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data == "confirm_start_monitoring")
async def confirm_and_start_monitoring(callback: CallbackQuery, state: FSMContext):
    """Подтверждение и запуск мониторинга с автоматическим исполнением"""
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
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="copy_trade_back")]
            ]
        )
        await callback.message.edit_text(
            "❌ Приватный ключ не найден!\n"
            "Используйте /start для повторной регистрации.",
            reply_markup=kb
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
    
    await _start_monitoring_task(callback, state, tg_id, data, private_key, user_address, api_key, api_secret, api_passphrase)


@dp.callback_query(F.data == "continue_without_api")
async def continue_without_api(callback: CallbackQuery, state: FSMContext):
    """Продолжить мониторинг без API credentials"""
    tg_id = callback.from_user.id
    data = await state.get_data()
    
    private_key = await users_sql.get_private_key(tg_id)
    user_address = await users_sql.select_user_address(tg_id)
    
    await _start_monitoring_task(callback, state, tg_id, data, private_key, user_address, None, None, None)


async def _start_monitoring_task(callback, state, tg_id, data, private_key, user_address, api_key, api_secret, api_passphrase):
    """Запуск мониторинга кошелька с поддержкой режима без API"""

    # Основные настройки
    settings = Settings(
        exp_at=data.get("duration", 3600),
        started_at=int(time.time()),
        first_bet=data.get("first_bet", False),
        min_amount=data.get("min_amount", 1),
        min_quote=data.get("min_quote", 0.01),
        max_quote=data.get("max_quote", 0.99),
    )

    selected_wallet = data.get("selected_wallet", "")
    margin_amount = data.get("margin_amount", 0)

    scrapper = PolyScrapper(selected_wallet)

    api_enabled = all([api_key, api_secret, api_passphrase])

    poly_copy = PolyCopy(
        settings,
        scrapper,
        private_key=private_key,
        margin_amount=margin_amount,
        funder=user_address,
        api_key=api_key if api_enabled else None,
        api_secret=api_secret if api_enabled else None,
        api_passphrase=api_passphrase if api_enabled else None
    )

    # === CALLBACK ДЛЯ УВЕДОМЛЕНИЙ ===
    async def notify_found_position(position: Position, message: str, trade_executed: bool, trade_message: str):
        emoji = "✅" if trade_executed else "⏳"
        status = "Сделка исполнена!" if trade_executed else (
            "Только мониторинг" if not api_enabled else "Ошибка при исполнении"
        )

        text = (
            f"{emoji} **Найдена подходящая сделка!**\n\n"
            f"📝 {position.title}\n"
            f"💰 Сумма: ${round(position.usdcSize, 2)}\n"
            f"📊 Котировка: {round(position.price, 3)}\n"
            f"🎲 Исход: {position.outcome}\n"
        )

        if api_enabled:
            text += f"💵 Маржа: ${margin_amount}\n"

        text += f"\n📌 {message}\n🔄 {status}\n"

        if trade_message:
            text += f"\n🗒 {trade_message}"

        if api_enabled:
            text += "\n\nМониторинг продолжается..."
        else:
            text += "\n\n⚠️ Режим: только мониторинг (без автоисполнения)"

        try:
            await bot.send_message(tg_id, text, parse_mode="Markdown")
            logging.info(f"✅ Уведомление отправлено пользователю {tg_id}")
        except Exception as e:
            logging.error(f"❌ Ошибка отправки уведомления пользователю {tg_id}: {e}")

    async def run_monitoring():
        try:
            logging.info(f"🚀 Мониторинг запущен для пользователя {tg_id}")
            await poly_copy.monitoring_wallets(callback_func=notify_found_position)

            stats = poly_copy.get_statistics()
            summary = (
                f"✅ **Мониторинг завершен!**\n\n"
                f"📊 Найдено сделок: {stats['total_found']}\n"
                f"🎯 Отслежено рынков: {stats['markets_tracked']}"
            )

            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🔄 Запустить новый", callback_data="start_copy_trade")],
                    [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="main_menu")]
                ]
            )

            await bot.send_message(tg_id, summary, parse_mode="Markdown", reply_markup=kb)
            logging.info(f"✅ Мониторинг завершен для пользователя {tg_id}")

        except asyncio.CancelledError:
            stats = poly_copy.get_statistics()
            cancel_text = (
                f"🛑 **Мониторинг остановлен**\n\n"
                f"📊 Найдено сделок: {stats['total_found']}\n"
                f"🎯 Отслежено рынков: {stats['markets_tracked']}"
            )

            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🔄 Запустить новый", callback_data="start_copy_trade")],
                    [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="main_menu")]
                ]
            )

            await bot.send_message(tg_id, cancel_text, parse_mode="Markdown", reply_markup=kb)
            logging.info(f"🛑 Мониторинг остановлен пользователем {tg_id}")

        except Exception as e:
            err = f"❌ **Ошибка при мониторинге:** `{str(e)}`"
            logging.error(f"Ошибка мониторинга: {e}", exc_info=True)
            await bot.send_message(tg_id, err, parse_mode="Markdown")

        finally:
            if tg_id in active_monitors:
                del active_monitors[tg_id]
                logging.info(f"🧹 Очищен мониторинг пользователя {tg_id}")

    task = asyncio.create_task(run_monitoring())
    active_monitors[tg_id] = task

    # === UI ===
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🛑 Остановить мониторинг", callback_data="stop_monitoring")],
            [InlineKeyboardButton(text="📊 Статистика", callback_data="monitoring_stats")]
        ]
    )

    duration_text = f"{data.get('duration', 0) // 60} мин" if data.get('duration', 0) < 3600 else f"{data.get('duration', 0) // 3600} ч"
    mode_text = (
        "✨ Подходящие сделки будут автоматически исполняться!" if api_enabled
        else "⚠️ Режим: только мониторинг (уведомления без исполнения)"
    )

    try:
        await callback.message.edit_text(
            f"🚀 **Мониторинг запущен!**\n\n"
            f"👛 Кошелек: `{selected_wallet[:8]}...{selected_wallet[-6:]}`\n"
            f"⏱ Длительность: {duration_text}\n"
            f"💵 Маржа: ${margin_amount}\n\n"
            f"{mode_text}\n\n"
            f"Вы получите уведомление о каждой сделке.",
            parse_mode="Markdown",
            reply_markup=kb
        )
    except Exception as e:
        logging.warning(f"⚠️ Не удалось отредактировать сообщение: {e}")
        await bot.send_message(
            tg_id,
            f"🚀 **Мониторинг запущен!**\n\n"
            f"👛 Кошелек: `{selected_wallet[:8]}...{selected_wallet[-6:]}`\n"
            f"⏱ Длительность: {duration_text}\n"
            f"💵 Маржа: ${margin_amount}\n\n"
            f"{mode_text}\n\n"
            f"Вы получите уведомление о каждой сделке.",
            parse_mode="Markdown",
            reply_markup=kb
        )

    await state.set_state(CopyTradeState.monitoring)
    await callback.answer("✅ Мониторинг запущен!")


@dp.callback_query(F.data == "stop_monitoring")
async def stop_monitoring(callback: CallbackQuery, state: FSMContext):
    """Остановка мониторинга с выводом статистики"""
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


@dp.callback_query(F.data == "monitoring_stats")
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


# ============== НАВИГАЦИОННЫЕ ОБРАБОТЧИКИ ==============

@dp.callback_query(F.data == "back_to_wallet_select")
async def back_to_wallet_select(callback: CallbackQuery, state: FSMContext):
    await start_copy_trade_flow(callback, state)


@dp.callback_query(F.data == "back_to_minquote")
async def back_to_minquote(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    max_quote = data.get("max_quote", 0.99)
    fake_callback_data = f"minquote_{data.get('min_quote', 0.01)}"
    callback.data = fake_callback_data
    await min_quote_selected(callback, state)


@dp.callback_query(F.data == "back_to_duration")
async def back_to_duration(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.update_data(selected_wallet=data.get("selected_wallet"))
    fake_callback_data = types.CallbackQuery(
        id=callback.id,
        from_user=callback.from_user,
        chat_instance=callback.chat_instance,
        data=f"select_wallet_0"
    )
    await wallet_selected(callback, state)


@dp.callback_query(F.data == "back_to_minamount")
async def back_to_minamount(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    duration = data.get("duration", 3600)
    fake_callback_data = f"duration_{duration}"
    callback.data = fake_callback_data
    await duration_selected(callback, state)


@dp.callback_query(F.data == "back_to_firstbet")
async def back_to_firstbet(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    min_amount = data.get("min_amount", 1)
    fake_callback_data = f"minamount_{min_amount}"
    callback.data = fake_callback_data
    await min_amount_selected(callback, state)


async def main():
    try:
        await users_sql.create_tables()
        await set_commands(bot)
        await dp.start_polling(bot)
    except Exception as e:
        logging.exception("Fatal error in bot:")
    finally:
        await bot.session.close()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())