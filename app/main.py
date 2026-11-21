"""Application factory.

Run locally with::

    uv run uvicorn app.main:create_app --factory --reload

``--factory`` tells Uvicorn to *call* ``create_app()`` to get the application,
instead of importing a module-level ``app`` object. That keeps importing this
module free of side effects. Each test can also build a fresh application, so
no state leaks between tests. It is the same idea as NestJS's
``NestFactory.create(AppModule)``.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api.middleware.request_context import RequestContextMiddleware
from app.api.routes import health
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.session import create_engine, create_sessionmaker


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup/shutdown hook (like NestJS ``onModuleInit``/``onApplicationShutdown``).

    Everything before ``yield`` runs once at startup, everything after it once
    at shutdown. Disposing the engine closes pooled connections cleanly, so
    Postgres doesn't keep sessions from a stopped container around.
    """
    yield
    await app.state.engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and configure a new FastAPI application instance.

    ``settings`` is injected by tests. In normal runs it is read from the
    environment here, at startup, so invalid configuration stops the process
    before it accepts any traffic.
    """
    settings = settings or get_settings()
    configure_logging(settings)

    app = FastAPI(
        title="NexusRAG",
        version=__version__,
        description="Distributed enterprise Retrieval-Augmented Generation platform",
        debug=settings.debug,
        lifespan=lifespan,
        # None disables the interactive docs and the OpenAPI schema endpoint.
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    app.state.settings = settings
    # The engine is created here, not in `lifespan`: creating it opens no
    # connection, and it is then available even where lifespan events don't
    # run (in-process test clients).
    app.state.engine = create_engine(settings)
    app.state.sessionmaker = create_sessionmaker(app.state.engine)

    app.add_middleware(RequestContextMiddleware)
    app.include_router(health.router)
    return app
