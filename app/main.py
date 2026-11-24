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

import httpx
from fastapi import FastAPI

from app import __version__
from app.api.middleware.request_context import RequestContextMiddleware
from app.api.routes import health, me
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.core.readiness import (
    ReadinessCheck,
    postgres_probe,
    qdrant_probe,
    redis_probe,
    s3_probe,
)
from app.core.redis import create_redis_client
from app.db.migrations import expected_head
from app.db.session import create_engine, create_sessionmaker
from app.storage.s3 import create_s3_client


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup/shutdown hook (like NestJS ``onModuleInit``/``onApplicationShutdown``).

    Everything before ``yield`` runs once at startup, everything after it once
    at shutdown: close every client so connections are released cleanly.
    """
    yield
    await app.state.http.aclose()
    await app.state.redis.aclose()
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

    # Clients are created here, not in `lifespan`: creating them opens no
    # connection (each connects on first use), and they are then available
    # even where lifespan events don't run (in-process test clients).
    app.state.engine = create_engine(settings)
    app.state.sessionmaker = create_sessionmaker(app.state.engine)
    app.state.redis = create_redis_client(settings)
    app.state.http = httpx.AsyncClient(timeout=settings.readiness_timeout_seconds)
    app.state.s3 = create_s3_client(settings)
    app.state.readiness_checks = [
        ReadinessCheck("postgres", postgres_probe(app.state.engine, expected_head())),
        ReadinessCheck("redis", redis_probe(app.state.redis)),
        ReadinessCheck(
            "qdrant",
            qdrant_probe(
                app.state.http,
                str(settings.qdrant_url),
                settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None,
            ),
        ),
        ReadinessCheck("object_storage", s3_probe(app.state.s3, settings.s3_bucket)),
    ]

    app.add_middleware(RequestContextMiddleware)
    app.include_router(health.router)
    app.include_router(me.router)
    return app
