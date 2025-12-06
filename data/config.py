import os
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

class DBSettings:
    def __init__(self):
        self.host = os.getenv("DB_HOST")
        self.port = os.getenv("DB_PORT")
        self.user = os.getenv("DB_USER")
        self.password = os.getenv("DB_PASSWORD")
        self.name = os.getenv("DB_NAME")

    @property
    def url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.name}"
        )


class Config:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN")
    ATTEMPS: int = 3
    DELAY: int = 15
