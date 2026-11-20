"""Request-ID and access-log middleware.

For every HTTP request this middleware:

1. takes the caller's ``X-Request-ID`` header if it is safe, or generates one;
2. binds it to the request's *context* so every log line emitted while
   handling the request carries ``request_id``, without passing it around;
3. echoes it in the response header (clients and support can quote it);
4. logs one ``request.completed`` line with status and duration.

It is written as a plain ASGI middleware rather than Starlette's
``BaseHTTPMiddleware``. The plain form doesn't buffer or wrap the response
stream, which matters for the Server-Sent Events used by the query API later.
"""

import re
import time
import uuid

import structlog
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"
# Accept only short, plain IDs. Anything else (newlines, control characters,
# megabyte-long values) could forge or corrupt log lines, so it is replaced.
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")

logger = structlog.get_logger(__name__)


def resolve_request_id(incoming: str | None) -> str:
    """Return the incoming ID if it is safe, otherwise a fresh UUID4."""
    if incoming and _SAFE_REQUEST_ID.fullmatch(incoming):
        return incoming
    return str(uuid.uuid4())


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":  # lifespan / websocket events pass straight through
            await self.app(scope, receive, send)
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        request_id = resolve_request_id(headers.get(REQUEST_ID_HEADER.lower()))

        # contextvars are per-task: concurrent requests each see their own values.
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        status_code = 500  # if the app crashes before sending a response
        start = time.perf_counter()

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            logger.info(
                "request.completed",
                method=scope["method"],
                path=scope["path"],
                status_code=status_code,
                duration_ms=round((time.perf_counter() - start) * 1000, 2),
            )
            structlog.contextvars.clear_contextvars()
