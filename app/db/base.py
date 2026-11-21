"""Declarative base shared by every ORM model.

The naming convention gives every constraint and index a predictable name
(``uq_tenants_slug``, ``ck_tenants_status`` …). Without it, Postgres invents
names such as ``tenants_slug_key``. Alembic then can't reliably find a
constraint to drop or alter in a later migration, and names can differ between
databases created at different times.
"""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
