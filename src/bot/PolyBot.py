import sys
import asyncio
from rich.table import Table

from aiogram import Bot, Dispatcher, types
from aiogram.types import BotCommand
from aiogram.filters import Command
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

from db.users import UsersSQL
from db.manager import AsyncDatabaseManager

from src.core.PolyScrapper import PolyScrapper
from data.config import BOT_TOKEN

bot = Bot(BOT_TOKEN)
storage = MemoryStorage() 
dp = Dispatcher(storage=storage)
db = AsyncDatabaseManager('users.db')
users_sql = UsersSQL(db)


class RegisterState(StatesGroup):
    waiting_for_address = State()

async def set_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="Начать работу / регистрация"),
        BotCommand(command="positions", description="Показать все активные позиции"),
        BotCommand(command="leaderboard", description="Позиция в рейтинге"),
        BotCommand(command="copy_trade", description="Отслеживать новые сделки"),
        BotCommand(command="reset_address", description="Заменить ваш основной кошелек"),
    ]
    await bot.set_my_commands(commands)

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    tg_id = message.from_user.id
    address = await users_sql.select_user_address(tg_id)

    if address is None:
        await message.answer(
            "👋 Привет! Твоего Polymarket адреса нет в базе.\n"
            "Пожалуйста, отправь его сюда (например: `0x1234...abcd`):",
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
    text = (
        f"**Данные по вашему аккаунту - {lead['userName']}**\n"
        f"🏆 Место в топе: {lead['rank']}\n"
        f"👛 Обьем за все время: {round(lead['vol'], 3)}\n"
        f"💸 Реализованный PnL: {round(lead['pnl'], 3)}"
    )
    await message.answer(text, parse_mode="Markdown")

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

async def main():
    try:
        await users_sql.create_tables()
        await set_commands(bot)
        await dp.start_polling(bot)
    except Exception as e:
        print(e)
    finally:
        await bot.session.close()
        # await users_sql.clear_users()
        await db.close()

if __name__ == "__main__":
    asyncio.run(main())
