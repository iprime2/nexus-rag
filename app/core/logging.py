"""Structured logging.

Every log line is a set of key/value pairs ("event dict"), rendered as one
JSON object per line in production:

    {"event": "request.completed", "level": "info", "request_id": "…",
     "method": "GET", "path": "/health/live", "status_code": 200,
     "duration_ms": 1.4, "timestamp": "2026-11-20T17:00:00.000Z"}

Machines can filter and aggregate fields (``status_code >= 500``,
``request_id = …``) instead of grepping free text.

Two sources of log records go through the same pipeline:

* our code logs with ``structlog.get_logger()``;
* libraries (Uvicorn, later SQLAlchemy, Celery, httpx) log with Python's
  standard ``logging`` module. ``ProcessorFormatter`` renders their records
  through the same processors, so *all* output has one format.
"""

import logging
import sys
from collections.abc import MutableMapping
from typing import Any, TextIO

import structlog
from structlog.typing import EventDict, Processor, WrappedLogger

from app.core.config import Settings

# Keys whose values must never appear in logs (case-insensitive substring match).
_SENSITIVE_KEY_PARTS = ("password", "secret", "token", "api_key", "apikey", "authorization")
REDACTED = "[REDACTED]"


def redact_sensitive_values(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
    """Replace values of sensitive-looking keys, including in nested dicts.

    A safety net, not a licence: code should still never log secrets on
    purpose. It catches accidents like ``log.info("call", headers=headers)``.
    """

    def scrub(mapping: MutableMapping[str, Any]) -> None:
        for key, value in mapping.items():
            if any(part in key.lower() for part in _SENSITIVE_KEY_PARTS):
                mapping[key] = REDACTED
            elif isinstance(value, MutableMapping):
                scrub(value)

    scrub(event_dict)
    return event_dict


def configure_logging(settings: Settings, stream: TextIO | None = None) -> None:
    """Configure structlog and the standard library to emit one log format.

    ``stream`` defaults to stdout (containers log to stdout; the platform
    collects it). Tests pass a ``StringIO`` to inspect the real output.
    """
    shared_processors: list[Processor] = [
        # Pull in request-scoped fields (request_id, …) bound with bind_contextvars().
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        redact_sensitive_values,
    ]

    renderer: Processor
    if settings.log_format == "json":
        # Tracebacks become structured dicts instead of multi-line text,
        # so one exception stays one JSON line.
        shared_processors.append(structlog.processors.dict_tracebacks)
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    # Our own loggers: run the shared processors, then hand over to stdlib.
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )

    # One handler on the root logger renders records from both sources.
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,  # applied to stdlib-only records
        processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer],
    )
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level)

    # Uvicorn installs its own handlers; route its records through ours instead.
    for name in ("uvicorn", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True
    # Uvicorn's access log is replaced by our request middleware, which also
    # records the request ID and duration.
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers = []
    access_logger.propagate = False
