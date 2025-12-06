import asyncio
import logging
from typing import Dict

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand

from data.config import Config
from db.database import database

logging.basicConfig(level=logging.INFO)

bot = Bot(token=Config.BOT_TOKEN)
dp = Dispatcher()
active_monitors: Dict[int, asyncio.Task] = {}


async def set_commands(bot: Bot):
    """Установка команд бота"""
    commands = [
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="copy_trade", description="Отслеживать и повторять новые сделки кошельков"),
    ]
    await bot.set_my_commands(commands)


async def main():
    try:
        await database.setup()
        
        await set_commands(bot)
        
        from src.bot.handlers import start, positions, leaderboard, copy_trade, charts
        
        dp.include_router(start.router)
        dp.include_router(positions.router)
        dp.include_router(leaderboard.router)
        dp.include_router(copy_trade.router)
        dp.include_router(charts.router)
        
        print("🚀 Бот запущен")
        await dp.start_polling(bot)
        
    except Exception as e:
        logging.exception("❌ Критическая ошибка в боте:")
        
    finally:
        await bot.session.close()
        await database.close()