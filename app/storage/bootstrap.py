"""One-off job: make sure the documents bucket exists.

    python -m app.storage.bootstrap

Run by the ``storage-init`` service in Docker Compose before the API starts.
"""

import structlog

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.storage.s3 import create_s3_client, ensure_bucket


def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    created = ensure_bucket(create_s3_client(settings), settings.s3_bucket)
    structlog.get_logger(__name__).info(
        "storage.bucket_ready", bucket=settings.s3_bucket, created=created
    )


if __name__ == "__main__":
    main()
