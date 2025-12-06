from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from data.config import DBSettings

db_settings = DBSettings()

async_engine = create_async_engine(
    db_settings.url,
    echo=True,
    future=True,
)

async_session = async_sessionmaker(
    bind=async_engine,
    expire_on_commit=False,
)
