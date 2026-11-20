"""Tests for structured logging and the request-context middleware.

They capture the *real* rendered output (JSON lines in a StringIO), so they
check what actually reaches stdout, not a mocked logger.
"""

import asyncio
import io
import json
import logging
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
import structlog
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.types import Message, Receive, Scope, Send

from app.api.middleware.request_context import RequestContextMiddleware, resolve_request_id
from app.core.config import Environment, Settings
from app.core.logging import REDACTED, configure_logging
from app.main import create_app


@pytest.fixture
def log_stream() -> Iterator[io.StringIO]:
    stream = io.StringIO()
    yield stream
    structlog.contextvars.clear_contextvars()


def json_lines(stream: io.StringIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in stream.getvalue().splitlines() if line]


def make_settings(**overrides: Any) -> Settings:
    return Settings(_env_file=None, environment=Environment.TEST, **overrides)


def make_app(stream: io.StringIO) -> FastAPI:
    """App whose logs go to `stream`, plus a route that logs from inside a handler."""
    app = create_app(make_settings())
    configure_logging(make_settings(), stream=stream)  # redirect output after the factory

    @app.get("/work")
    async def work() -> dict[str, str]:
        structlog.get_logger("test").info("work.done", items=3)
        return {"ok": "yes"}

    return app


async def request(app: FastAPI, path: str, headers: dict[str, str] | None = None) -> Any:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        return await client.get(path, headers=headers)


# ------------------------------------------------------------- log format


def test_json_output_has_standard_fields(log_stream: io.StringIO) -> None:
    configure_logging(make_settings(), stream=log_stream)

    structlog.get_logger("nexus.test").info("thing.happened", count=2)

    [line] = json_lines(log_stream)
    assert line["event"] == "thing.happened"
    assert line["count"] == 2
    assert line["level"] == "info"
    assert line["logger"] == "nexus.test"
    assert line["timestamp"].endswith("Z")  # ISO 8601, UTC


def test_stdlib_logs_use_the_same_json_format(log_stream: io.StringIO) -> None:
    configure_logging(make_settings(), stream=log_stream)

    logging.getLogger("uvicorn.error").warning("library message")

    [line] = json_lines(log_stream)
    assert line["event"] == "library message"
    assert line["level"] == "warning"


def test_log_level_filters_lower_levels(log_stream: io.StringIO) -> None:
    configure_logging(make_settings(log_level="WARNING"), stream=log_stream)

    log = structlog.get_logger("nexus.test")
    log.info("hidden")
    log.warning("shown")

    assert [line["event"] for line in json_lines(log_stream)] == ["shown"]


def test_exceptions_are_logged_as_one_structured_line(log_stream: io.StringIO) -> None:
    configure_logging(make_settings(), stream=log_stream)

    try:
        raise ValueError("boom")
    except ValueError:
        structlog.get_logger().exception("operation.failed")

    [line] = json_lines(log_stream)
    assert line["exception"][0]["exc_type"] == "ValueError"


def test_console_format_is_not_json(log_stream: io.StringIO) -> None:
    configure_logging(make_settings(log_format="console"), stream=log_stream)

    structlog.get_logger().info("hello.console")

    output = log_stream.getvalue()
    assert "hello.console" in output
    with pytest.raises(json.JSONDecodeError):
        json.loads(output)


# ------------------------------------------------------------- redaction


def test_sensitive_values_are_redacted_including_nested(log_stream: io.StringIO) -> None:
    configure_logging(make_settings(), stream=log_stream)

    structlog.get_logger().info(
        "provider.call",
        api_key="sk-live-123",
        headers={"Authorization": "Bearer abc", "Accept": "json"},
        user_password="hunter2",  # noqa: S106 - fake secret: proves it gets redacted
        model="some-model",
    )

    [line] = json_lines(log_stream)
    assert line["api_key"] == REDACTED
    assert line["user_password"] == REDACTED
    assert line["headers"]["Authorization"] == REDACTED
    assert line["headers"]["Accept"] == "json"
    assert line["model"] == "some-model"
    assert "sk-live-123" not in log_stream.getvalue()


# ------------------------------------------------------------- request IDs


async def test_generates_request_id_and_returns_it(log_stream: io.StringIO) -> None:
    response = await request(make_app(log_stream), "/health/live")

    request_id = response.headers["X-Request-ID"]
    assert uuid.UUID(request_id)  # a valid generated UUID
    [access] = [line for line in json_lines(log_stream) if line["event"] == "request.completed"]
    assert access["request_id"] == request_id
    assert access["method"] == "GET"
    assert access["path"] == "/health/live"
    assert access["status_code"] == 200
    assert access["duration_ms"] >= 0


async def test_reuses_a_safe_incoming_request_id(log_stream: io.StringIO) -> None:
    response = await request(make_app(log_stream), "/health/live", {"X-Request-ID": "abc-123"})

    assert response.headers["X-Request-ID"] == "abc-123"


@pytest.mark.parametrize(
    "unsafe",
    [
        "abc\nlevel=error fake log line",  # log injection attempt
        "x" * 129,  # too long
        "has spaces",
        "",
    ],
)
def test_unsafe_incoming_request_ids_are_replaced(unsafe: str) -> None:
    resolved = resolve_request_id(unsafe)

    assert resolved != unsafe
    assert uuid.UUID(resolved)


async def test_logs_inside_a_handler_carry_the_request_id(log_stream: io.StringIO) -> None:
    response = await request(make_app(log_stream), "/work", {"X-Request-ID": "req-42"})

    assert response.status_code == 200
    [work] = [line for line in json_lines(log_stream) if line["event"] == "work.done"]
    assert work["request_id"] == "req-42"
    assert work["items"] == 3


async def test_concurrent_requests_do_not_mix_request_ids(log_stream: io.StringIO) -> None:
    app = make_app(log_stream)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        await asyncio.gather(
            *(client.get("/work", headers={"X-Request-ID": f"req-{i}"}) for i in range(20))
        )

    pairs = {
        (line["event"], line["request_id"])
        for line in json_lines(log_stream)
        if line["event"] in {"work.done", "request.completed"}
    }
    for i in range(20):
        assert ("work.done", f"req-{i}") in pairs
        assert ("request.completed", f"req-{i}") in pairs
    assert len(pairs) == 40


async def test_context_is_cleared_after_the_request(log_stream: io.StringIO) -> None:
    await request(make_app(log_stream), "/health/live", {"X-Request-ID": "req-old"})

    structlog.get_logger().info("background.event")

    [line] = [line for line in json_lines(log_stream) if line["event"] == "background.event"]
    assert "request_id" not in line


async def test_unhandled_error_is_logged_with_status_500(log_stream: io.StringIO) -> None:
    app = make_app(log_stream)

    @app.get("/explode")
    async def explode() -> None:
        raise RuntimeError("unexpected")

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://t"
    ) as client:
        response = await client.get("/explode")

    assert response.status_code == 500
    [access] = [line for line in json_lines(log_stream) if line["event"] == "request.completed"]
    assert access["status_code"] == 500


async def test_non_http_scopes_pass_through_untouched() -> None:
    seen: list[str] = []

    async def inner_app(scope: Scope, receive: Receive, send: Send) -> None:
        seen.append(scope["type"])

    async def receive() -> Message:
        return {"type": "lifespan.startup"}

    async def send(message: Message) -> None:
        return None

    await RequestContextMiddleware(inner_app)({"type": "lifespan"}, receive, send)

    assert seen == ["lifespan"]
