"""API-key authentication end to end: CLI → database → HTTP dependency."""

import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.api_keys import generate_api_key
from app.auth.service import create_tenant, issue_api_key, revoke_api_key
from app.cli import main as cli_main
from app.core.config import Settings
from app.db.models import ApiKey, Tenant
from app.main import create_app

pytestmark = pytest.mark.integration


@pytest.fixture
async def client(db_settings: Settings) -> AsyncIterator[AsyncClient]:
    app = create_app(db_settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c
    await app.state.engine.dispose()
    await app.state.redis.aclose()
    await app.state.http.aclose()


async def new_tenant_with_key(
    session_factory: async_sessionmaker[AsyncSession], slug: str
) -> tuple[Tenant, str, uuid.UUID]:
    async with session_factory() as session:
        tenant = await create_tenant(session, slug, slug.title())
        issued = await issue_api_key(session, tenant.id, "test")
        await session.commit()
    return tenant, issued.plaintext, issued.api_key.id


def auth(key: str) -> dict[str, str]:
    return {"Authorization": f"ApiKey {key}"}


# ------------------------------------------------------------------ happy path


async def test_valid_key_resolves_its_tenant(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    tenant, key, key_id = await new_tenant_with_key(session_factory, "acme")

    response = await client.get("/v1/me", headers=auth(key))

    assert response.status_code == 200
    assert response.json() == {
        "tenant_id": str(tenant.id),
        "tenant_slug": "acme",
        "api_key_id": str(key_id),
    }


async def test_each_key_only_sees_its_own_tenant(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    acme, acme_key, _ = await new_tenant_with_key(session_factory, "acme")
    globex, globex_key, _ = await new_tenant_with_key(session_factory, "globex")

    assert (await client.get("/v1/me", headers=auth(acme_key))).json()["tenant_id"] == str(acme.id)
    assert (await client.get("/v1/me", headers=auth(globex_key))).json()["tenant_id"] == str(
        globex.id
    )


async def test_only_the_hash_is_stored(session_factory: async_sessionmaker[AsyncSession]) -> None:
    _, key, key_id = await new_tenant_with_key(session_factory, "acme")

    async with session_factory() as session:
        stored = await session.scalar(select(ApiKey).where(ApiKey.id == key_id))
        dump = await session.scalar(text("SELECT row_to_json(api_keys)::text FROM api_keys"))

    assert stored is not None
    assert stored.key_prefix == key[:12]
    assert key not in (dump or "")


# ------------------------------------------------------------------ rejections


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "ApiKey not-a-key"},
        {"Authorization": f"ApiKey {generate_api_key()}"},  # well-formed but unknown
    ],
)
async def test_missing_malformed_or_unknown_keys_get_the_same_401(
    client: AsyncClient, headers: dict[str, str]
) -> None:
    response = await client.get("/v1/me", headers=headers)

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "ApiKey"
    assert response.json() == {"detail": "Missing or invalid API key"}


async def test_revoked_key_is_rejected(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    _, key, key_id = await new_tenant_with_key(session_factory, "acme")
    assert (await client.get("/v1/me", headers=auth(key))).status_code == 200

    async with session_factory() as session:
        assert await revoke_api_key(session, key_id) is True
        assert await revoke_api_key(session, key_id) is False  # idempotent
        await session.commit()

    assert (await client.get("/v1/me", headers=auth(key))).status_code == 401


async def test_suspended_tenant_is_forbidden(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    tenant, key, _ = await new_tenant_with_key(session_factory, "acme")
    async with session_factory() as session:
        await session.execute(
            update(Tenant).where(Tenant.id == tenant.id).values(status="suspended")
        )
        await session.commit()

    response = await client.get("/v1/me", headers=auth(key))

    assert response.status_code == 403


async def test_deleting_a_tenant_deletes_its_keys(
    client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    tenant, key, _ = await new_tenant_with_key(session_factory, "acme")
    async with session_factory() as session:
        await session.execute(text("DELETE FROM tenants WHERE id = :id"), {"id": tenant.id})
        await session.commit()
        remaining = await session.scalar(text("SELECT count(*) FROM api_keys"))

    assert remaining == 0
    assert (await client.get("/v1/me", headers=auth(key))).status_code == 401


# ------------------------------------------------------------------ CLI


def test_cli_creates_tenant_and_key_and_revokes_it(
    db_settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli_main(["create-tenant", "--slug", "cli-co", "--name", "CLI Co"], db_settings) == 0
    assert cli_main(["create-api-key", "--tenant", "cli-co", "--name", "ci"], db_settings) == 0
    out = capsys.readouterr().out
    key_id = out.split("api key id: ")[1].split()[0]
    assert "nxr_" in out

    assert cli_main(["revoke-api-key", key_id], db_settings) == 0
    assert cli_main(["revoke-api-key", key_id], db_settings) == 1  # already revoked
    assert cli_main(["create-tenant", "--slug", "cli-co", "--name", "Dup"], db_settings) == 1
    assert cli_main(["create-api-key", "--tenant", "nope", "--name", "x"], db_settings) == 1
