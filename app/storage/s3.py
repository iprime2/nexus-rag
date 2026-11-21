"""S3 client factory and bucket bootstrap.

The same code talks to SeaweedFS locally and to Amazon S3 in production; only
``NEXUS_S3_ENDPOINT_URL`` and the credentials differ (ADR-0005, ADR-0011).

boto3 is synchronous. Async code calls it through ``asyncio.to_thread`` so a
slow S3 request never blocks the event loop. A boto3 *client* is thread-safe
and is created once per process.
"""

from typing import TYPE_CHECKING

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import Settings

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


def create_s3_client(settings: Settings) -> "S3Client":
    key_id, secret = settings.s3_access_key_id, settings.s3_secret_access_key
    return boto3.client(
        "s3",
        endpoint_url=str(settings.s3_endpoint_url) if settings.s3_endpoint_url else None,
        region_name=settings.s3_region,
        config=Config(
            connect_timeout=settings.readiness_timeout_seconds,
            read_timeout=10,
            retries={"max_attempts": 2, "mode": "standard"},
            # Path-style URLs (http://host/bucket/key): what local S3 servers expect.
            s3={"addressing_style": "path"},
        ),
        # None (the default) means: use the standard AWS credential chain, e.g. the IAM role.
        aws_access_key_id=key_id.get_secret_value() if key_id else None,
        aws_secret_access_key=secret.get_secret_value() if secret else None,
    )


def ensure_bucket(client: "S3Client", bucket: str) -> bool:
    """Create ``bucket`` if it doesn't exist. Returns True if it was created.

    Idempotent, so safe to run on every deployment. On AWS the bucket is
    created by infrastructure code (Terraform, Phase 8) instead.
    """
    try:
        client.head_bucket(Bucket=bucket)
        return False
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") not in {"404", "NoSuchBucket", "NotFound"}:
            raise  # e.g. 403: wrong credentials. Don't mask it as "missing".
    client.create_bucket(Bucket=bucket)
    return True
