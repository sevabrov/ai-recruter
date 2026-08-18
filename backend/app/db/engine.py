"""
The connection pool.

One engine per process, created at startup and disposed at shutdown. Sessions are
short-lived and never shared between tasks: the pipeline runs its stages
concurrently, and a session is not safe across `await` boundaries in more than one
task, so every repository call opens its own.

`expire_on_commit=False` because the repository converts rows into Pydantic models
inside the transaction and returns those — nothing is read back from an expired
instance after the commit.
"""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings

SessionFactory = async_sessionmaker[AsyncSession]


def create_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.database_url,
        echo=settings.db_echo,
        # The pipeline bounds itself per stage (§52); the pool has to be able to
        # serve that many stage workers plus the requests coming in meanwhile.
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        # A connection killed by a database restart is replaced instead of raising
        # on first use — the API survives `docker compose restart postgres`.
        pool_pre_ping=True,
        pool_recycle=1800,
    )


def create_session_factory(engine: AsyncEngine) -> SessionFactory:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
