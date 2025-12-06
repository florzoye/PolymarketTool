import asyncio
from typing import Dict
from data.config import Config

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand

from db.sqlite.users import UsersSQL
from db.sqlite.manager import AsyncDatabaseManager


bot = Bot(token=Config.BOT_TOKEN)
dp = Dispatcher()

db = AsyncDatabaseManager('data/users.db')
users_sql = UsersSQL(db)

active_monitors: Dict[int, asyncio.Task] = {}


async def set_commands(bot: Bot):
    """Установка команд бота"""
    commands = [
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="copy_trade", description="Отслеживать и повторять новые сделки кошельков"),
    ]
    await bot.set_my_commands(commands)