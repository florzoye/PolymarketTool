import os
import sys
import asyncio

sys.path.insert(0, os.path.dirname(__file__))

from src.bot.cfg import main

if __name__ == "__main__":
    asyncio.run(main())