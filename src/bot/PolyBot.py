import sys
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

from db.users import UsersSQL
from db.manager import AsyncDatabaseManager
from data.config import BOT_TOKEN

bot = Bot(BOT_TOKEN)
storage = MemoryStorage() 
dp = Dispatcher(storage=storage)
db = AsyncDatabaseManager('users.db')
users_sql = UsersSQL(db)


class RegisterState(StatesGroup):
    waiting_for_address = State()


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
        await message.answer("✅ Всё отлично, ты уже зарегистрирован!")

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
    await message.answer(f"✅ Отлично! Адрес `{address}` сохранён.", parse_mode="Markdown")


async def main():
    try:
        await users_sql.create_tables()
        await dp.start_polling(bot)
    except Exception as e:
        print(e)
    finally:
        await bot.session.close()
        # await users_sql.clear_users()
        await db.close()

if __name__ == "__main__":
    asyncio.run(main())
