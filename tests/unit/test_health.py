from fastapi import FastAPI
from httpx import AsyncClient

from app import __version__
from app.main import create_app


async def test_live_returns_ok_and_version(client: AsyncClient) -> None:
    response = await client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


async def test_live_is_documented_in_openapi(client: AsyncClient) -> None:
    schema = (await client.get("/openapi.json")).json()

    operation = schema["paths"]["/health/live"]["get"]
    assert "200" in operation["responses"]
    assert schema["info"]["version"] == __version__


async def test_unknown_route_returns_404(client: AsyncClient) -> None:
    response = await client.get("/does-not-exist")

    assert response.status_code == 404


def test_factory_returns_independent_instances() -> None:
    first, second = create_app(), create_app()

    assert isinstance(first, FastAPI)
    assert first is not second
