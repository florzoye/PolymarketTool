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

    # Тип БД: "sqlite" или "postgresql"
    DATABASE_TYPE: str = os.getenv("DATABASE_TYPE", "sqlite")
    
    # SQLite
    SQLITE_PATH: str = os.getenv("SQLITE_PATH", "database.db")
    
    # PostgreSQL - вариант 1: полный URL
    DATABASE_URL: str = os.getenv("DATABASE_URL")
    
    # PostgreSQL - вариант 2: через DBSettings
    DB = DBSettings()
    
    @classmethod
    def get_database_url(cls) -> str:
        """
        Возвращает URL для подключения к БД
        Приоритет: DATABASE_URL > DBSettings
        """
        if cls.DATABASE_URL:
            return cls.DATABASE_URL
        return cls.DB.url