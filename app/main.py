"""Application factory.

Run locally with::

    uv run uvicorn app.main:create_app --factory --reload

``--factory`` tells Uvicorn to *call* ``create_app()`` to get the application,
instead of importing a module-level ``app`` object. That keeps importing this
module free of side effects. Each test can also build a fresh application, so
no state leaks between tests. It is the same idea as NestJS's
``NestFactory.create(AppModule)``.
"""

from fastapi import FastAPI

from app import __version__
from app.api.routes import health
from app.core.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and configure a new FastAPI application instance.

    ``settings`` is injected by tests. In normal runs it is read from the
    environment here, at startup, so invalid configuration stops the process
    before it accepts any traffic.
    """
    settings = settings or get_settings()

    app = FastAPI(
        title="NexusRAG",
        version=__version__,
        description="Distributed enterprise Retrieval-Augmented Generation platform",
        debug=settings.debug,
        # None disables the interactive docs and the OpenAPI schema endpoint.
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    app.state.settings = settings
    app.include_router(health.router)
    return app
