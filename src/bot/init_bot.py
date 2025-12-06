import asyncio
import logging

from src.bot.cfg import bot, dp, db, users_sql, set_commands
from src.bot.handlers import start, positions, leaderboard, copy_trade, charts

logging.basicConfig(level=logging.INFO)


async def main():
    try:
        await users_sql.create_tables()
        await set_commands(bot)
        
        dp.include_router(start.router)
        dp.include_router(positions.router)
        dp.include_router(leaderboard.router)
        dp.include_router(copy_trade.router)
        dp.include_router(charts.router)
        
        await dp.start_polling(bot)
    except Exception as e:
        logging.exception("Fatal error in bot:")
    finally:
        await bot.session.close()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())