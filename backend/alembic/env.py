"""
Alembic environment.

The URL comes from the application's settings (spec §22 — configuration is
environment, never a checked-in string), unless the caller sets one on the config,
which is what `app/db/bootstrap.py` and the test suite do.
"""

import asyncio

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.db.tables import Base

config = context.config

#: Autogenerate compares the live database against this.
target_metadata = Base.metadata


def _url() -> str:
    return config.get_main_option("sqlalchemy.url", "") or get_settings().database_url


def _configure(**kwargs) -> None:
    context.configure(
        target_metadata=target_metadata,
        # Catch column type drift, not just added and dropped tables.
        compare_type=True,
        compare_server_default=True,
        **kwargs,
    )


def run_migrations_offline() -> None:
    """`alembic upgrade head --sql` — emit the DDL without connecting."""
    _configure(url=_url(), literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def _run(connection) -> None:
    _configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(_url(), poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
