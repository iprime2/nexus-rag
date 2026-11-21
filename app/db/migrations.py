"""Which migration should the database be at?

The readiness check compares the database's ``alembic_version`` with the
newest migration shipped in this build. An API whose code expects a newer
schema than the database has must not take traffic (it would fail on the first
query touching a new column).
"""

from functools import lru_cache
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


@lru_cache
def expected_head(alembic_ini: Path = Path("alembic.ini")) -> str:
    """The head revision of the migrations next to ``alembic.ini``.

    The path is relative to the working directory: the repository root
    locally, ``/app`` in the container image.
    """
    if not alembic_ini.is_file():
        raise FileNotFoundError(f"{alembic_ini.resolve()} not found; run from the project root")
    head = ScriptDirectory.from_config(Config(str(alembic_ini))).get_current_head()
    if head is None:
        raise RuntimeError("No Alembic migrations found")
    return head
