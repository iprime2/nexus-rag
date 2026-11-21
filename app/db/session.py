"""Engine and session factories.

* **Engine**: owns the connection pool. One per process, created at startup,
  disposed at shutdown. Creating it does *not* open a connection; the first
  query does.
* **Session**: a unit of work borrowed from the pool for one request (or one
  task). It is cheap to create and must never be shared between concurrent
  requests.

NestJS/TypeORM comparison: the engine is the ``DataSource``; a session is
roughly a ``QueryRunner`` / ``EntityManager`` for one transaction.
"""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout_seconds,
        # Test each pooled connection with a cheap round trip before using it.
        # After a database restart or failover, dead connections are replaced
        # transparently instead of failing the next request.
        pool_pre_ping=True,
        connect_args={"connect_timeout": 5},
    )


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    # expire_on_commit=False: objects stay readable after commit. With async
    # sessions, an expired attribute would trigger lazy I/O on access, which
    # fails outside an awaited context.
    return async_sessionmaker(engine, expire_on_commit=False)
