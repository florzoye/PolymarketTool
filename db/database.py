import logging
from data.config import Config
from db.factory import UsersFactory, DatabaseType
from db.sqlite.manager import AsyncDatabaseManager
from db.sqlalchemy.session import SQLAlchemyManager


class Database:
    """Менеджер базы данных"""
    
    def __init__(self):
        self.repo = None
        self.sqlite_manager = None
        self.sqlalchemy_manager = None
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def setup(self):
        
        if Config.DATABASE_TYPE == "sqlite":
            self.sqlite_manager = AsyncDatabaseManager(Config.SQLITE_PATH)
            await self.sqlite_manager.connect()
            
            self.repo = UsersFactory.create(
                DatabaseType.SQLITE, 
                self.sqlite_manager
            )
            await self.repo.create_tables()
            self.logger.info(f"✅ SQLite подключена: {Config.SQLITE_PATH}")
            
        else:
            self.sqlalchemy_manager = SQLAlchemyManager()
            self.sqlalchemy_manager.init()

            session = self.sqlalchemy_manager.get_session()

            self.repo = UsersFactory.create(
                DatabaseType.SQLALCHEMY, 
                session
            )

            db_url = Config.get_database_url()
            safe_url = db_url.split('@')[1] if '@' in db_url else db_url
            self.logger.info(f"✅ PostgreSQL подключена: {safe_url}")
    
    def get(self):
        if self.repo is None:
            raise RuntimeError(
                "Database not initialized. Call database.setup() first"
            )
        return self.repo
    
    async def close(self):
        if self.sqlite_manager:
            await self.sqlite_manager.close()
            self.logger.info("✅ SQLite соединение закрыто")
        
        if self.sqlalchemy_manager:
            await self.sqlalchemy_manager.close()


database = Database()