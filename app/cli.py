"""Operator command line (tenant and API key administration).

    uv run python -m app.cli create-tenant --slug acme --name "Acme Corp"
    uv run python -m app.cli create-api-key --tenant acme --name ci-uploader
    uv run python -m app.cli revoke-api-key <key-id>

In Docker Compose: ``docker compose exec api python -m app.cli …``.

Tenant creation is an operator action, not a public API endpoint (see
docs/api-specification.md §2).
"""

import argparse
import asyncio
import sys
import uuid
from collections.abc import Sequence

from sqlalchemy.exc import IntegrityError

from app.auth.service import create_tenant, get_tenant_by_slug, issue_api_key, revoke_api_key
from app.core.config import Settings, get_settings
from app.db.session import create_engine, create_sessionmaker


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)

    tenant = commands.add_parser("create-tenant", help="create a tenant")
    tenant.add_argument("--slug", required=True, help="lowercase, digits and hyphens")
    tenant.add_argument("--name", required=True)

    key = commands.add_parser("create-api-key", help="issue an API key (printed once)")
    key.add_argument("--tenant", required=True, help="tenant slug")
    key.add_argument("--name", required=True, help="label, e.g. ci-uploader")

    revoke = commands.add_parser("revoke-api-key", help="revoke an API key")
    revoke.add_argument("key_id", type=uuid.UUID)
    return parser


async def run(args: argparse.Namespace, settings: Settings) -> int:
    engine = create_engine(settings)
    try:
        async with create_sessionmaker(engine)() as session:
            if args.command == "create-tenant":
                try:
                    tenant = await create_tenant(session, args.slug, args.name)
                    await session.commit()
                except IntegrityError:
                    print(
                        f"error: tenant {args.slug!r} exists or the slug is invalid",
                        file=sys.stderr,
                    )
                    return 1
                print(f"created tenant {tenant.slug} ({tenant.id})")

            elif args.command == "create-api-key":
                found = await get_tenant_by_slug(session, args.tenant)
                if found is None:
                    print(f"error: no tenant {args.tenant!r}", file=sys.stderr)
                    return 1
                issued = await issue_api_key(session, found.id, args.name)
                await session.commit()
                print(f"api key id: {issued.api_key.id}")
                print(f"api key:    {issued.plaintext}")
                print("Store this key now. It is not saved and cannot be shown again.")

            elif args.command == "revoke-api-key":
                revoked = await revoke_api_key(session, args.key_id)
                await session.commit()
                if not revoked:
                    print("error: key not found or already revoked", file=sys.stderr)
                    return 1
                print(f"revoked api key {args.key_id}")
        return 0
    finally:
        await engine.dispose()


def main(argv: Sequence[str] | None = None, settings: Settings | None = None) -> int:
    args = build_parser().parse_args(argv)
    return asyncio.run(run(args, settings or get_settings()))


if __name__ == "__main__":
    sys.exit(main())
