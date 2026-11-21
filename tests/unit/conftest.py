import pytest


@pytest.fixture(autouse=True)
def _fake_database_password(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit tests never connect to Postgres, but Settings requires a password.

    Scoped to tests/unit only, so integration tests use the real one from the
    environment.
    """
    monkeypatch.setenv("NEXUS_POSTGRES_PASSWORD", "unit-test-password")
