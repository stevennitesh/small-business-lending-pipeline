from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from pipelines.storage.artifact_models import (
    S3ObjectClientProtocol,
    S3RawArtifactReference,
    StorageBackend,
)


def default_s3_client():
    """Return the default boto3 S3 client."""
    import boto3

    return boto3.client("s3")


def normalized_s3_bucket(bucket: str, *, empty_message: str) -> str:
    """Normalize a bucket or s3://bucket value into a bare bucket name."""
    normalized_bucket = bucket.removeprefix("s3://").strip("/")
    if not normalized_bucket:
        raise ValueError(empty_message)
    return normalized_bucket


def require_s3_location(storage_backend: StorageBackend, *, message: str) -> None:
    """Raise when a storage location is not S3-backed."""
    if storage_backend != "s3":
        raise ValueError(message)


def put_s3_object(
    client: S3ObjectClientProtocol,
    *,
    bucket: str,
    key: str,
    body: Any,
) -> None:
    """Write one object to S3 through the configured client."""
    client.put_object(Bucket=bucket, Key=key, Body=body)


def read_s3_object(
    client: S3ObjectClientProtocol,
    *,
    bucket: str,
    key: str,
) -> bytes:
    """Read one S3 object body as bytes."""
    response = client.get_object(Bucket=bucket, Key=key)
    return response["Body"].read()


def parse_s3_uri(uri: str) -> S3RawArtifactReference:
    """Parse and validate an s3://bucket/key URI."""
    parsed = urlparse(uri)
    if parsed.scheme != "s3" or not parsed.netloc or not parsed.path.strip("/"):
        raise ValueError(f"Invalid S3 URI: {uri}")
    return S3RawArtifactReference(bucket=parsed.netloc, key=parsed.path.strip("/"))
