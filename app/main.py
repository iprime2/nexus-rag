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


def create_app() -> FastAPI:
    """Build and configure a new FastAPI application instance."""
    app = FastAPI(
        title="NexusRAG",
        version=__version__,
        description="Distributed enterprise Retrieval-Augmented Generation platform",
    )
    app.include_router(health.router)
    return app
