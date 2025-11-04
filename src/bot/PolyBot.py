import asyncio
import logging

from aiogram import F
from aiogram.filters import Command
from aiogram.types import BotCommand, CallbackQuery
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from db.users import UsersSQL
from db.manager import AsyncDatabaseManager
from src.bot.states import TrackSettings, RegisterState

from src.core.PolyScrapper import PolyScrapper
from data.config import BOT_TOKEN

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# БД
db = AsyncDatabaseManager('users.db')
users_sql = UsersSQL(db)


async def set_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="Начать работу / регистрация"),
        BotCommand(command="positions", description="Показать все активные позиции"),
        BotCommand(command="leaderboard", description="Позиция в рейтинге"),
        BotCommand(command="copy_trade", description="Отслеживать и повторять новые сделки кошельков"),
        BotCommand(command="reset_address", description="Заменить ваш основной кошелек"),
    ]
    await bot.set_my_commands(commands)


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
        await message.answer("Всё отлично, ты уже зарегистрирован!")


@dp.message(Command("positions"))
async def cmd_pos(message: types.Message):
    tg_id = message.from_user.id
    address = await users_sql.select_user_address(tg_id)

    if not address:
        await message.answer("❌ Адрес не найден. Сначала введите его через /start.")
        return

    await message.answer("⏳ Получаю данные с Polymarket...")

    scrapper = PolyScrapper(address)
    positions = await scrapper.get_account_positions()

    if not positions:
        await message.answer("😕 Похоже, у тебя нет активных позиций на Polymarket.")
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
    await message.answer(text, parse_mode="Markdown")


@dp.message(Command('leaderboard'))
async def cmd_leaderboard(message: types.Message):
    tg_id = message.from_user.id
    address = await users_sql.select_user_address(tg_id)

    if not address:
        await message.answer("❌ Адрес не найден. Сначала введите его через /start.")
        return
    
    scrapper = PolyScrapper(address)
    lead = await scrapper.check_leaderboard()

    # check_leaderboard ожидается как dict: безопасный доступ
    userName = lead.get('userName', 'Unknown')
    rank = lead.get('rank', '—')
    vol = lead.get('vol', 0)
    pnl = lead.get('pnl', 0)

    text = (
        f"**Данные по вашему аккаунту - {userName}**\n"
        f"🏆 Место в топе: {rank}\n"
        f"👛 Обьем за все время: {round(vol, 3)}\n"
        f"💸 Реализованный PnL: {round(pnl, 3)}"
    )
    await message.answer(text, parse_mode="Markdown")


@dp.message(Command('reset_address'))
async def cmd_reset_address(message: types.Message, state: FSMContext):
    tg_id = message.from_user.id
    address = await users_sql.select_user_address(tg_id)
    if not address:
        await message.answer("❌ Адрес не найден. Сначала введите его через /start.")
        return
    
    await message.answer(
        f'Сейчас ваш адресс - {address}\n'
        f'Если желаете поменять, пришлите новый в чат.'
    )
    await state.set_state(RegisterState.reset_address)


@dp.message(Command('copy_trade'))
async def cmd_copy_trade(message: types.Message):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='Кошельки на треке', callback_data='track_wallets')],
            [InlineKeyboardButton(text='Позиции кошельков на треке', callback_data='track_positions')],
            [InlineKeyboardButton(text='Запустить copy-trade для конкретных кошельков', callback_data='start_copy_trade')]
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
    await message.answer(f"Адрес `{address}` сохранён.", parse_mode="Markdown")


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
    await message.answer(f"Адрес `{address}` сохранён.", parse_mode="Markdown")


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


@dp.message(TrackSettings.waiting_for_count)
async def get_deal_count(message: types.Message, state: FSMContext):
    try:
        count = int(message.text)
        if count <= 0 or count > 10:
            raise ValueError
    except ValueError:
        await message.answer("⚠️ Введите число от 1 до 10.")
        return

    await state.update_data(count=count)

    back_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="copy_trade_back")]
        ]
    )

    # Используем message.answer, т.к. это ответ на сообщение пользователя
    await message.answer(
        "Теперь введите минимальную маржу сделки (например, 20.5)",
        reply_markup=back_kb
    )
    await state.set_state(TrackSettings.waiting_for_min_value)


@dp.message(TrackSettings.waiting_for_min_value)
async def get_min_value(message: types.Message, state: FSMContext):
    try:
        min_value = float(message.text)
        if min_value < 0:
            raise ValueError
    except ValueError:
        await message.answer("⚠️ Введите корректное число (например, 10.0)")
        return

    user_data = await state.get_data()
    count = int(user_data.get("count", 5))
    await state.clear()

    text = (
        f"✅ Настройки применены!\n\n"
        f"Показываю до **{count}** сделок с минимальным value ≥ **{min_value}$**.\n\n"
    )
    track_addresses = await users_sql.get_track_wallets(message.from_user.id)

    for address in track_addresses:
        scrapper = PolyScrapper(address)
        positions = await scrapper.get_account_positions() or []
        positions = positions[-count:]

        lead = await scrapper.check_leaderboard()
        name = lead.get('userName') 

        text += f'Позиции {name} (`{address}`):\n'
        for j, pos in enumerate(positions, 1):
            try:
                size = float(pos.get('size', 0) or 0)
            except (TypeError, ValueError):
                size = 0
            if size <= min_value:
                continue

            title = pos.get("title", "Без названия")
            current = round(float(pos.get("currentValue", 0)), 2)
            pnl = round(float(pos.get("cashPnl", 0)), 2)
            percent = round(float(pos.get("percentRealizedPnl", 0) or 0), 2)
            text += (
                f"**{j}. {title}**\n"
                f"💰 Текущая стоимость: `${current}`\n"
                f"📈 PnL: `${pnl}` ({percent}%)\n"
                f"───────────────────────\n"
            )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="copy_trade_back")]
        ]
    )

    await message.answer(text, parse_mode="Markdown", reply_markup=kb)


# ----------------- CALLBACK -----------------
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

    text = f"**У вас {len(track_addresses)} кошельков на треке, вот их показатели:**\n\n"
    for i, address in enumerate(track_addresses, 1):
        scrapper = PolyScrapper(address)
        lead_data = await scrapper.check_leaderboard()
        value = await scrapper.get_value_user()

        # безопасный доступ к полям
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
    await callback.answer()


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

    await callback.message.edit_text(
        "Сколько последних сделок показать? (например, 5)",
        reply_markup=back_kb
    )
    await state.set_state(TrackSettings.waiting_for_count)
    await callback.answer()


@dp.callback_query(F.data == "copy_trade_back")
async def copy_trade_back(callback: CallbackQuery, state: FSMContext):
    await state.clear()

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text='Кошельки на треке', callback_data='track_wallets')],
            [InlineKeyboardButton(text='Позиции кошельков на треке', callback_data='track_positions')],
            [InlineKeyboardButton(text='Запустить copy-trade для конкретных кошельков', callback_data='start_copy_trade')]
        ]
    )

    await callback.message.edit_text("Меню copy-trade на Polymarket!", reply_markup=kb)
    await callback.answer()


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
