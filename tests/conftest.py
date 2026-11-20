"""Shared pytest fixtures.

A fixture is a function that pytest calls to provide a test with something
it needs. A test asks for one by naming it as a parameter. This plays the
role of NestJS's ``Test.createTestingModule()``, without a DI container.
"""

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.fixture
def app() -> FastAPI:
    """A fresh application per test, so tests can't share state."""
    return create_app()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """An HTTP client that calls the app in-process.

    ``ASGITransport`` hands each request straight to the ASGI app. No server
    and no network are involved, so tests are fast and deterministic, while
    every request still goes through FastAPI's full routing, validation and
    serialization.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
