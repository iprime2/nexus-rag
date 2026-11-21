"""FastAPI dependency that provides one database session per request.

Usage in a route::

    async def handler(session: DbSession) -> ...:
        session.add(obj)
        await session.commit()

Transactions are committed **explicitly** by the code that owns the business
operation, not automatically for every request. Later, streaming endpoints
(SSE) must not hold a transaction open while waiting on an LLM, and some
operations need several separate transactions (see database-design §5).

When the request ends, the ``async with`` closes the session: uncommitted
work is rolled back and the connection returns to the pool, even if the
handler raised.
"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    sessionmaker: async_sessionmaker[AsyncSession] = request.app.state.sessionmaker
    async with sessionmaker() as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_session)]
