"""Alembic environment.

Reads the DB URL from the application settings (DATABASE_URL env var) and
uses the SQLAlchemy 2.x declarative metadata from `models.Base`.
"""
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

import sys
from pathlib import Path

# Make the backend package importable when running `alembic` from /backend.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import Base, settings  # noqa: E402
import models  # noqa: F401, E402  — registers all tables on Base.metadata

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Inject the DB URL from app settings (supports both sync and async URLs).
db_url = settings.database_url
if db_url.startswith("postgresql+asyncpg://"):
    db_url = db_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
config.set_main_option("sqlalchemy.url", db_url)

target_metadata = Base.metadata


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
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
