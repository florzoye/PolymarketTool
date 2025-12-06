import sys
from pathlib import Path
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import db.sqlalchemy.models
from data.config import DBSettings
from db.sqlalchemy.models import Base, Users

target_metadata = Base.metadata

print("=" * 50)
print(f"Tables in metadata: {list(Base.metadata.tables.keys())}")
print(f"Users table exists: {'users' in Base.metadata.tables}")
if 'users' in Base.metadata.tables:
    users_table = Base.metadata.tables['users']
    print(f"Users columns: {[c.name for c in users_table.columns]}")
print("=" * 50)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

sync_url = DBSettings().url.replace("asyncpg", "psycopg2")
config.set_main_option("sqlalchemy.url", sync_url)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()