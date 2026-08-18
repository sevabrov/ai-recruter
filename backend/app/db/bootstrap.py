"""
Bringing a database up to date.

The API migrates itself on startup, so `docker compose up -d backend` against an
empty volume is still one command and no separate step can be forgotten. The
schema is versioned from the first table onwards — `alembic/versions/` is the
record of what the database looks like, and `tests/test_persistence.py` runs the
suite through those same migrations rather than a `create_all` shortcut, so the
migrations cannot quietly drift from `tables.py`.

Once Phase 7 adds a second process (the Celery worker), migrations should be taken
out of startup or wrapped in a `pg_advisory_lock`: two processes booting at once
would otherwise race for the same revision.
"""

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.core.logging import get_logger

log = get_logger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
ALEMBIC_DIR = BACKEND_DIR / "alembic"


def alembic_config(database_url: str) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(ALEMBIC_DIR))
    # ConfigParser interpolates `%`, and passwords are allowed to contain it.
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


def upgrade_schema(database_url: str) -> None:
    """Blocking: `alembic upgrade head`."""
    command.upgrade(alembic_config(database_url), "head")


async def upgrade_schema_async(database_url: str) -> None:
    # Alembic's async environment calls `asyncio.run`, which cannot be nested in a
    # running loop — hence a worker thread rather than an await.
    await asyncio.to_thread(upgrade_schema, database_url)
    log.info("schema_up_to_date")
