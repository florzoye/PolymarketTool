import time
import asyncio
import logging
from typing import Dict
from itertools import islice

from aiogram import F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram import Bot, Dispatcher, types
from aiogram.types import BotCommand, CallbackQuery, FSInputFile
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from db.users import UsersSQL
from db.manager import AsyncDatabaseManager
from src.bot.states import TrackSettings, RegisterState, CopyTradeState

from src.core.PolyCopy import PolyCopy
from src.models.settings import Settings
from src.models.position import Position
from src.core.PolyCharts import PolyCharts 
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
async def show_positions(callback: CallbackQuery, state: FSMContext):
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
        try:
            await callback.message.edit_text(
                "😕 Похоже, у тебя нет активных позиций на Polymarket.",
                reply_markup=kb
            )
        except Exception:
            await callback.message.answer(
                "😕 Похоже, у тебя нет активных позиций на Polymarket.",
                reply_markup=kb
            )
        return

    await state.update_data(current_positions=positions)

    max_show = 10
    display_positions = positions[:max_show]

    timestamp =  time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
    
    text = f"📊 Топ {len(display_positions)} позиций по адресу `{address}`:\n\n"

    for i, pos in enumerate(display_positions, 1):
        title = pos.get("title", "Без названия")
        current = round(float(pos.get("currentValue", 0)), 2)
        pnl = round(float(pos.get("cashPnl", 0)), 2)
        percent = round(float(pos.get("percentRealizedPnl", 0) or 0), 2)

        pnl_emoji = "📈" if pnl >= 0 else "📉"

        text += (
            f"{i}. {title[:60]}\n"
            f"💰 Стоимость: `${current}`\n"
            f"{pnl_emoji} PnL: `${pnl}` ({percent}%)\n"
            f"🌐 График: нажми кнопку ниже\n"
            f"───────────────────────\n"
        )
    
    text += f"\n`⏱ Обновлено: {timestamp}`"

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            *[
                [InlineKeyboardButton(text=f"📉 График {i+1}", callback_data=f"chart_{i}")]
                for i in range(len(display_positions))
            ],
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="show_positions")],
            [InlineKeyboardButton(text="❌ Закрыть позицию", callback_data="select_position_to_close")],
            [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="main_menu")]
        ]
    )

    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    except Exception as e:
        error_msg = str(e).lower()
        
        if "no text in the message" in error_msg or "message to edit not found" in error_msg:
            await callback.message.answer(text, reply_markup=kb, parse_mode="Markdown")
        elif "message is not modified" in error_msg:
            await callback.message.answer(text, reply_markup=kb, parse_mode="Markdown")
        else:
            logging.error(f"Ошибка при редактировании сообщения в show_positions: {e}")
            await callback.message.answer(text, reply_markup=kb, parse_mode="Markdown")



@dp.callback_query(F.data == "select_position_to_close")
async def select_position_to_close(callback: CallbackQuery, state: FSMContext):
    """Показывает список позиций для закрытия"""
    data = await state.get_data()
    positions = data.get("current_positions", [])
    
    if not positions:
        await callback.answer("❌ Нет активных позиций", show_alert=True)
        return
    
    keyboard = []
    for i, pos in enumerate(positions[:15]):  
        title = pos.get("title", "Без названия")[:40]
        current = round(float(pos.get("currentValue", 0)), 2)
        pnl = round(float(pos.get("cashPnl", 0)), 2)
        
        pnl_emoji = "📈" if pnl >= 0 else "📉"
        button_text = f"{pnl_emoji} {title}... (${current})"
        
        keyboard.append([InlineKeyboardButton(
            text=button_text,
            callback_data=f"close_pos_{i}"
        )])
    
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="show_positions")])
    
    kb = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    await callback.message.edit_text(
        "❌ **Выберите позицию для закрытия:**\n\n"
        "⚠️ **Внимание!** Закрытие позиции необратимо.\n"
        "Убедитесь что выбрали правильную позицию.",
        parse_mode="Markdown",
        reply_markup=kb
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("close_pos_"))
async def confirm_close_position(callback: CallbackQuery, state: FSMContext):
    """Подтверждение закрытия позиции"""
    pos_index = int(callback.data.split("_")[-1])
    data = await state.get_data()
    positions = data.get("current_positions", [])
    
    if pos_index >= len(positions):
        await callback.answer("❌ Ошибка: позиция не найдена", show_alert=True)
        return
    
    position = positions[pos_index]
    title = position.get("title", "Без названия")
    current = round(float(position.get("currentValue", 0)), 2)
    size = float(position.get("size", 0))
    pnl = round(float(position.get("cashPnl", 0)), 2)
    percent = round(float(position.get("percentRealizedPnl", 0) or 0), 2)
    
    await state.update_data(closing_position_index=pos_index)
    
    pnl_emoji = "📈" if pnl >= 0 else "📉"
    
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, закрыть позицию", callback_data="execute_close_position")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="select_position_to_close")]
        ]
    )
    
    text = (
        "⚠️ **Подтверждение закрытия позиции**\n\n"
        f"📝 **Название:** {title}\n"
        f"💰 **Текущая стоимость:** ${current}\n"
        f"📊 **Размер:** {size}\n"
        f"{pnl_emoji} **PnL:** ${pnl} ({percent}%)\n\n"
        f"❗ Вы уверены, что хотите закрыть эту позицию?"
    )
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    await callback.answer()


@dp.callback_query(F.data == "execute_close_position")
async def execute_close_position(callback: CallbackQuery, state: FSMContext):
    """Исполнение закрытия позиции"""
    tg_id = callback.from_user.id
    data = await state.get_data()
    
    pos_index = data.get("closing_position_index")
    positions = data.get("current_positions", [])
    
    if pos_index is None or pos_index >= len(positions):
        await callback.answer("❌ Ошибка: позиция не найдена", show_alert=True)
        return
    
    position = positions[pos_index]
    title = position.get("title", "Без названия")
    
    private_key = await users_sql.get_private_key(tg_id)
    user_address = await users_sql.select_user_address(tg_id)
    api_key, api_secret, api_passphrase = await users_sql.get_api_credentials(tg_id)
    
    if not private_key:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="show_positions")]
            ]
        )
        await callback.message.edit_text(
            "❌ Приватный ключ не найден!\n"
            "Для закрытия позиций нужен приватный ключ.",
            reply_markup=kb
        )
        await callback.answer()
        return
    
    await callback.message.edit_text(
        f"⏳ **Закрываю позицию...**\n\n"
        f"📝 {title}\n\n"
        f"Пожалуйста, подождите...",
        parse_mode="Markdown"
    )
    
    try:
        scrapper = PolyScrapper(user_address)
        
        temp_settings = Settings(
            exp_at=60,
            started_at=int(time.time()),
            first_bet=False,
            min_amount=1,
            min_quote=0.01,
            max_quote=0.99
        )
        
        poly_copy = PolyCopy(
            temp_settings,
            scrapper,
            private_key=private_key,
            margin_amount=1,  # Не важно для закрытия
            funder=user_address,
            api_key=api_key,
            api_secret=api_secret,
            api_passphrase=api_passphrase
        )
        
        current_positions = await scrapper.get_account_positions()
        
        actual_pos = next((p for p in current_positions if p.get('title') == title), None)
        
        if not actual_pos:
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="⬅️ К позициям", callback_data="show_positions")]
                ]
            )
            await callback.message.edit_text(
                f"❌ **Позиция не найдена**\n\n"
                f"Возможно она уже закрыта или изменилась.",
                parse_mode="Markdown",
                reply_markup=kb
            )
            await callback.answer()
            return
        
        token_id = actual_pos.get('asset')
        size = float(actual_pos.get('size'))
        
        if not token_id:
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="⬅️ К позициям", callback_data="show_positions")]
                ]
            )
            await callback.message.edit_text(
                f"❌ **Ошибка: не найден token_id**\n\n"
                f"Невозможно закрыть позицию без token_id.",
                parse_mode="Markdown",
                reply_markup=kb
            )
            await callback.answer()
            return
        
        success = await poly_copy.close_position(token_id, size)
        
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Обновить позиции", callback_data="show_positions")],
                [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="main_menu")]
            ]
        )
        
        if success:
            pnl = round(float(position.get("cashPnl", 0)), 2)
            percent = round(float(position.get("percentRealizedPnl", 0) or 0), 2)
            
            text = (
                f"✅ **Позиция успешно закрыта!**\n\n"
                f"📝 {title}\n"
                f"💰 Финальный PnL: ${pnl} ({percent}%)\n\n"
                f"Позиция больше не отображается в вашем портфеле."
            )
        else:
            text = (
                f"❌ **Ошибка при закрытии позиции**\n\n"
                f"📝 {title}\n\n"
                f"Возможные причины:\n"
                f"• Недостаточно средств\n"
                f"• Проблемы с API\n"
                f"• Позиция уже закрыта\n\n"
                f"Попробуйте позже или проверьте на polymarket.com"
            )
        
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
        await callback.answer()
        
    except Exception as e:
        logging.error(f"Ошибка закрытия позиции: {e}")
        
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ К позициям", callback_data="show_positions")]
            ]
        )
        
        await callback.message.edit_text(
            f"❌ **Произошла ошибка:**\n\n"
            f"`{str(e)}`\n\n"
            f"Попробуйте позже.",
            parse_mode="Markdown",
            reply_markup=kb
        )
        await callback.answer()

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


# ============== COPY TRADE START ==============

@dp.callback_query(F.data == "start_copy_trade")
async def start_copy_trade_flow(callback: CallbackQuery, state: FSMContext):
    """Начало быстрой настройки copy-trade через inline кнопки"""
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
    
    await state.update_data(
        track_addresses=track_addresses,
        selected_wallet=None,
        duration=3600,  
        min_amount=5,
        first_bet=False,
        min_quote=0.01,
        max_quote=1.0,
        margin_amount=10
    )
    
    await show_quick_setup_menu(callback.message, state)
    await callback.answer()


async def show_quick_setup_menu(message, state: FSMContext):
    """Показывает меню быстрой настройки со всеми параметрами"""
    data = await state.get_data()
    track_addresses = data.get("track_addresses", [])
    
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
            [InlineKeyboardButton(
                text=f"👛 Кошелек: {wallet_text}",
                callback_data="quick_select_wallet"
            )],
            [InlineKeyboardButton(
                text=f"⏱ Длительность: {duration_text}",
                callback_data="quick_duration"
            )],
            [InlineKeyboardButton(
                text=f"💰 Мин. сумма: ${min_amount}",
                callback_data="quick_min_amount"
            )],
            [InlineKeyboardButton(
                text=f"🎯 Первые ставки: {first_bet_text}",
                callback_data="quick_first_bet"
            )],
            [InlineKeyboardButton(
                text=f"📊 Котировки: {min_quote} - {max_quote}",
                callback_data="quick_quotes"
            )],
            [InlineKeyboardButton(
                text=f"💵 Маржа: ${margin_amount}",
                callback_data="quick_margin"
            )],

            [InlineKeyboardButton(
                text=f"🛑 SL (%): {sl_percent}%",
                callback_data="quick_sl"
            )],
            [InlineKeyboardButton(
                text=f"🎯 TP (%): {tp_percent}%",
                callback_data="quick_tp"
            )],

            [InlineKeyboardButton(
                text="🚀 Запустить мониторинг",
                callback_data="quick_start_monitoring"
            )],
            [InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data="copy_trade_back"
            )]
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

@dp.callback_query(F.data == "quick_sl")
async def quick_sl_menu(callback: CallbackQuery, state: FSMContext):
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


@dp.callback_query(F.data == "quick_tp")
async def quick_tp_menu(callback: CallbackQuery, state: FSMContext):
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

@dp.callback_query(F.data.startswith("set_sl_"))
async def set_sl(callback: CallbackQuery, state: FSMContext):
    value = int(callback.data.split("_")[2])
    await state.update_data(sl_percent=value)

    await show_quick_setup_menu(callback.message, state)

@dp.callback_query(F.data.startswith("set_tp_"))
async def set_tp(callback: CallbackQuery, state: FSMContext):
    value = int(callback.data.split("_")[2])
    await state.update_data(tp_percent=value)

    await show_quick_setup_menu(callback.message, state)


@dp.callback_query(F.data == "quick_select_wallet")
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
            callback_data=f"qw_{i}"  # qw = quick wallet
        )])
    
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="quick_back")])
    
    kb = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    await callback.message.edit_text(
        "👛 **Выберите кошелек для мониторинга:**",
        parse_mode="Markdown",
        reply_markup=kb
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("qw_"))
async def quick_wallet_selected(callback: CallbackQuery, state: FSMContext):
    """Сохранение выбранного кошелька"""
    wallet_index = int(callback.data.split("_")[-1])
    data = await state.get_data()
    track_addresses = data.get("track_addresses", [])
    
    if wallet_index < len(track_addresses):
        await state.update_data(selected_wallet=track_addresses[wallet_index])
        await callback.answer("✅ Кошелек выбран")
    
    await show_quick_setup_menu(callback.message, state)


@dp.callback_query(F.data == "quick_duration")
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


@dp.callback_query(F.data.startswith("qd_"))
async def quick_duration_selected(callback: CallbackQuery, state: FSMContext):
    """Сохранение длительности"""
    duration = int(callback.data.split("_")[-1])
    await state.update_data(duration=duration)
    
    duration_text = f"{duration // 60} мин" if duration < 3600 else f"{duration // 3600} ч"
    await callback.answer(f"✅ Длительность: {duration_text}")
    
    await show_quick_setup_menu(callback.message, state)



@dp.callback_query(F.data == "quick_min_amount")
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


@dp.callback_query(F.data.startswith("qa_"))
async def quick_amount_selected(callback: CallbackQuery, state: FSMContext):
    """Сохранение минимальной суммы"""
    if callback.data == "qa_custom":
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="quick_back")]
            ]
        )
        
        await callback.message.edit_text(
            "✏️ **Ввод кастомной минимальной суммы**\n\n"
            "💰 Введите минимальную сумму ставки в долларах:\n\n"
            "Примеры: `3`, `7.5`, `15`\n\n"
            "⚠️ Минимум: $0.1\n"
            "⚠️ Максимум: $1000\n\n"
            "Отправьте число в чат:",
            parse_mode="Markdown",
            reply_markup=kb
        )
        await state.set_state(CopyTradeState.setting_custom_min_amount)
        await callback.answer()
        return
    
    min_amount = float(callback.data.split("_")[-1])
    await state.update_data(min_amount=min_amount)
    await callback.answer(f"✅ Мин. сумма: ${min_amount}")
    
    await show_quick_setup_menu(callback.message, state)


@dp.callback_query(F.data == "quick_first_bet")
async def quick_first_bet(callback: CallbackQuery, state: FSMContext):
    """Переключение фильтра первых ставок"""
    data = await state.get_data()
    current = data.get("first_bet", False)
    new_value = not current
    
    await state.update_data(first_bet=new_value)
    
    text = "✅ Теперь копируются только первые ставки" if new_value else "❌ Копируются все ставки"
    await callback.answer(text)
    
    await show_quick_setup_menu(callback.message, state)


@dp.callback_query(F.data == "quick_quotes")
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


@dp.callback_query(F.data.startswith("qq_"))
async def quick_quotes_selected(callback: CallbackQuery, state: FSMContext):
    """Сохранение диапазона котировок"""
    if callback.data == "qq_custom":
        data = await state.get_data()
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


@dp.callback_query(F.data == "quick_margin")
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


@dp.callback_query(F.data.startswith("qm_"))
async def quick_margin_selected(callback: CallbackQuery, state: FSMContext):
    """Сохранение маржи"""
    if callback.data == "qm_custom":
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="quick_back")]
            ]
        )
        
        await callback.message.edit_text(
            "✏️ **Ввод кастомной маржи**\n\n"
            "💰 Введите сумму в долларах (USD):\n\n"
            "Примеры: `15`, `75.5`, `333`\n\n"
            "⚠️ Минимум: $1\n"
            "⚠️ Максимум: $10000\n\n"
            "Отправьте число в чат:",
            parse_mode="Markdown",
            reply_markup=kb
        )
        await state.set_state(CopyTradeState.setting_custom_margin)
        await callback.answer()
        return
    
    margin_amount = float(callback.data.split("_")[-1])
    await state.update_data(margin_amount=margin_amount)
    await callback.answer(f"✅ Маржа: ${margin_amount}")
    
    await show_quick_setup_menu(callback.message, state)


@dp.callback_query(F.data == "quick_back")
async def quick_back(callback: CallbackQuery, state: FSMContext):
    """Возврат к главному меню быстрой настройки"""
    await show_quick_setup_menu(callback.message, state)
    await callback.answer()


@dp.callback_query(F.data == "quick_start_monitoring")
async def quick_start_monitoring(callback: CallbackQuery, state: FSMContext):
    """Запуск мониторинга из быстрой настройки"""
    data = await state.get_data()
    
    if not data.get("selected_wallet"):
        await callback.answer("❌ Выберите кошелек!", show_alert=True)
        return
    
    await confirm_and_start_monitoring(callback, state)


@dp.callback_query(F.data.startswith("chart_"))
async def send_chart(callback: CallbackQuery, state: FSMContext):
    """Отправка графика с кнопкой возврата"""
    index = int(callback.data.split("_")[1])
    tg_id = callback.from_user.id

    user_data = await state.get_data()
    positions = user_data.get("current_positions")

    if not positions or index >= len(positions):
        await callback.answer("❌ Ошибка: позиция не найдена", show_alert=True)
        return

    pos = positions[index]
    condition_id = pos.get("asset") 
    slug = pos.get("title", "chart").replace(" ", "_")[:40]

    await callback.answer("⏳ Строю график...")

    try:
        charts = PolyCharts(
            condition_id=condition_id,
            slug=slug,
            tg_id=tg_id
        )

        ok, path = await charts.create_chart()

        if not ok:
            await callback.message.answer(
                f"❌ Не удалось построить график:\n{path}",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="⬅️ К позициям", callback_data="show_positions")]
                    ]
                )
            )
            return

        nav_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Вернуться к позициям", callback_data="show_positions")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
            ]
        )

        await callback.message.answer_photo(
            photo=FSInputFile(path),
            caption=f"📉 График: {pos.get('title', '')}",
            reply_markup=nav_kb
        )
        
    except Exception as e:
        logging.error(f"Ошибка при создании графика: {e}")
        await callback.message.answer(
            f"❌ Произошла ошибка при создании графика",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="⬅️ К позициям", callback_data="show_positions")]
                ]
            )
        )


@dp.message(CopyTradeState.setting_custom_margin)
async def quick_custom_margin_input(message: types.Message, state: FSMContext):
    """Обработка кастомной маржи в быстрой настройке"""
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
        await state.clear()  

        await message.answer(
            f"✅ Маржа установлена: ${margin_amount}\n\n"
            "Возвращаюсь к настройкам..."
        )
        
        await show_quick_setup_menu_new_message(message, state)
        
    except ValueError:
        await message.answer(
            "⚠️ Неверный формат! Введите число (например: 15 или 75.5)"
        )


async def show_quick_setup_menu_new_message(message, state: FSMContext):
    """Показывает меню быстрой настройки в новом сообщении"""
    data = await state.get_data()
    track_addresses = data.get("track_addresses", [])
    
    selected_wallet = data.get("selected_wallet")
    duration = data.get("duration", 3600)
    min_amount = data.get("min_amount", 5)
    first_bet = data.get("first_bet", False)
    min_quote = data.get("min_quote", 0.01)
    max_quote = data.get("max_quote", 1.0)
    margin_amount = data.get("margin_amount", 10)
    
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
        f"💵 **Маржа на сделку:** ${margin_amount}\n\n"
        f"Когда всё готово - нажмите '🚀 Запустить мониторинг'"
    )
    
    await message.answer(text, parse_mode="Markdown", reply_markup=kb)


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

@dp.callback_query(F.data == "quick_setup_back")
async def quick_back(callback: CallbackQuery, state: FSMContext):
    await show_quick_setup_menu(callback.message, state)


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