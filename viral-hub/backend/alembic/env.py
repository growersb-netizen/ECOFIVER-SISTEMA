"""
Alembic env.py — configurado para SQLAlchemy async con autogenerate.
Lee DATABASE_SYNC_URL del .env (psycopg2 sync, que Alembic requiere para autogenerate).
"""

import asyncio
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import Connection
from alembic import context

# Importar Base y todos los modelos para que Alembic los detecte
from app.core.database import Base
# Importar todos los modelos explícitamente para que Alembic los detecte
import app.models.user          # noqa: F401
import app.models.workspace     # noqa: F401
import app.models.channel       # noqa: F401
import app.models.media         # noqa: F401
import app.models.publication   # noqa: F401

from app.core.config import get_settings

settings = get_settings()

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_SYNC_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
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
        do_run_migrations(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
