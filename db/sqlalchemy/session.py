from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from data.config import Config


class SQLAlchemyManager:
    
    def __init__(self):
        self.engine = None
        self.session_maker = None
    
    def init(self):
        if self.engine is not None:
            return  
        
        database_url = Config.get_database_url()
        
        self.engine = create_async_engine(
            database_url,
            echo=False,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
        
        self.session_maker = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        
        print(f"✅ SQLAlchemy engine initialized")
    
    def get_session(self) -> AsyncSession:
        if self.session_maker is None:
            raise RuntimeError(
                "SQLAlchemy не инициализирована, для начала init()"
            )
        
        return self.session_maker()
    
    async def close(self):
        if self.engine:
            await self.engine.dispose()
            print("✅ SQLAlchemy мотор остановлен")
    
    def get_engine(self):
        if self.engine is None:
            raise RuntimeError(
                "SQLAlchemy не инициализирована, для начала init()"
            )
        return self.engine


# Создаем единственный экземпляр менеджера
sqlalchemy_manager = SQLAlchemyManager()