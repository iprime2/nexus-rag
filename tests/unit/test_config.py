from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.core.config import Environment, Settings
from app.main import create_app


def test_defaults_are_safe_for_local_development(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("NEXUS_ENVIRONMENT", "NEXUS_DEBUG", "NEXUS_DOCS_ENABLED"):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None)

    assert settings.environment is Environment.LOCAL
    assert settings.debug is False
    assert settings.docs_enabled is True


def test_reads_prefixed_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_ENVIRONMENT", "staging")
    monkeypatch.setenv("NEXUS_DEBUG", "true")

    settings = Settings(_env_file=None)

    assert settings.environment is Environment.STAGING
    assert settings.debug is True  # the string "true" was converted to a bool


def test_unprefixed_variables_are_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEBUG", "true")

    assert Settings(_env_file=None).debug is False


def test_reads_dotenv_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("NEXUS_ENVIRONMENT=staging\nNEXUS_DOCS_ENABLED=false\n")

    settings = Settings(_env_file=env_file)

    assert settings.environment is Environment.STAGING
    assert settings.docs_enabled is False


def test_environment_variables_override_dotenv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("NEXUS_ENVIRONMENT=staging\n")
    monkeypatch.setenv("NEXUS_ENVIRONMENT", "test")

    assert Settings(_env_file=env_file).environment is Environment.TEST


def test_invalid_value_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEXUS_ENVIRONMENT", "prod")  # typo for "production"

    with pytest.raises(ValidationError, match="environment"):
        Settings(_env_file=None)


def test_unknown_key_in_dotenv_fails_fast(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("NEXUS_DEUBG=true\n")  # misspelled NEXUS_DEBUG

    with pytest.raises(ValidationError, match="deubg"):
        Settings(_env_file=env_file)


def test_debug_is_rejected_in_production() -> None:
    with pytest.raises(ValidationError, match="NEXUS_DEBUG must be false"):
        Settings(_env_file=None, environment=Environment.PRODUCTION, debug=True)


def test_settings_are_immutable() -> None:
    settings = Settings(_env_file=None)

    with pytest.raises(ValidationError):
        settings.debug = True  # type: ignore[misc]


def test_create_app_fails_fast_on_invalid_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core import config

    config.get_settings.cache_clear()
    monkeypatch.setenv("NEXUS_ENVIRONMENT", "not-an-environment")
    try:
        with pytest.raises(ValidationError):
            create_app()  # no settings injected: reads the environment at startup
    finally:
        config.get_settings.cache_clear()


async def test_docs_can_be_disabled() -> None:
    app = create_app(Settings(_env_file=None, docs_enabled=False))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        assert (await client.get("/docs")).status_code == 404
        assert (await client.get("/openapi.json")).status_code == 404
        assert (await client.get("/health/live")).status_code == 200


def test_env_example_is_valid_and_complete() -> None:
    """.env.example must load cleanly and document every setting."""
    example = Path(__file__).parents[2] / ".env.example"

    settings = Settings(_env_file=example)  # extra="forbid": unknown keys would fail

    documented = {
        line.split("=", 1)[0].removeprefix("NEXUS_").lower()
        for line in example.read_text().splitlines()
        if line.startswith("NEXUS_")
    }
    assert documented == set(type(settings).model_fields)
