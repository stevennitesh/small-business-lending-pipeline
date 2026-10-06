from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

import boto3
from botocore.exceptions import ClientError, EndpointConnectionError

from pipelines.load.s3_upload_items import (
    S3UploadItem,
    build_run_upload_items,
)
from pipelines.utils.paths import build_s3_uri


TRANSIENT_ERROR_CODES = {
    "RequestTimeout",
    "RequestTimeoutException",
    "ServiceUnavailable",
    "SlowDown",
    "Throttling",
    "ThrottlingException",
    "TooManyRequestsException",
}


class S3ClientProtocol(Protocol):
    """Minimal S3 client surface used by the upload route."""

    def upload_file(self, filename: str, bucket: str, key: str) -> None:
        """Upload one local file to an S3 bucket/key."""
        ...

    def put_object(self, **kwargs) -> Any:
        """Conditionally create an immutable raw object."""
        ...


@dataclass(frozen=True)
class S3UploadSummary:
    """Result of attempting to upload run artifacts to S3."""

    bucket: str | None
    uploaded_objects: tuple[str, ...]
    skipped: bool = False
    warning: str | None = None

    @property
    def uploaded_count(self) -> int:
        """Return the number of uploaded S3 objects."""
        return len(self.uploaded_objects)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the upload summary for flow output or CLI JSON."""
        return asdict(self)


class S3UploadRequiredError(RuntimeError):
    """Raised when a required cloud upload cannot complete."""


def upload_run_artifacts_to_s3(
    *,
    manifest_paths: list[Path | str],
    validation_result_path: Path | str,
    bucket: str | None,
    run_mode: str,
    dbt_artifact_paths: list[Path | str] | None = None,
    s3_client: S3ClientProtocol | None = None,
    max_attempts: int = 3,
    base_delay_seconds: float = 1.0,
) -> S3UploadSummary:
    """Build and upload all S3 artifacts for one pipeline run."""
    if run_mode not in {"local", "cloud"}:
        raise ValueError("run_mode must be 'local' or 'cloud'.")
    return upload_items_to_s3(
        build_run_upload_items(
            manifest_paths=manifest_paths,
            validation_result_path=validation_result_path,
            dbt_artifact_paths=dbt_artifact_paths,
        ),
        bucket=bucket,
        s3_client=s3_client,
        required=run_mode == "cloud",
        max_attempts=max_attempts,
        base_delay_seconds=base_delay_seconds,
    )


def upload_items_to_s3(
    items: list[S3UploadItem],
    *,
    bucket: str | None,
    s3_client: S3ClientProtocol | None = None,
    required: bool,
    max_attempts: int = 3,
    base_delay_seconds: float = 1.0,
) -> S3UploadSummary:
    """Upload prepared items with route-specific required/optional behavior."""
    if not bucket:
        warning = "S3 upload skipped because no S3 bucket is configured."
        if required:
            raise S3UploadRequiredError(warning)
        return S3UploadSummary(
            bucket=None,
            uploaded_objects=(),
            skipped=True,
            warning=warning,
        )

    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1.")

    client = s3_client or boto3.client("s3")
    uploaded_objects: list[str] = []
    for item in items:
        _validate_upload_item(item)
        try:
            _upload_with_retries(
                client,
                item,
                bucket=bucket,
                max_attempts=max_attempts,
                base_delay_seconds=base_delay_seconds,
            )
        except Exception as exc:
            # Local runs surface upload failures as warnings; cloud runs must fail
            # so downstream Snowflake loads do not point at missing S3 artifacts.
            message_prefix = (
                "required S3 upload failed" if required else "S3 upload failed"
            )
            message = f"{message_prefix} for {item.local_path}: {exc}"
            if required:
                raise S3UploadRequiredError(message) from exc
            return S3UploadSummary(
                bucket=bucket,
                uploaded_objects=tuple(uploaded_objects),
                skipped=False,
                warning=message,
            )
        uploaded_objects.append(build_s3_uri(bucket, item.s3_key))

    return S3UploadSummary(bucket=bucket, uploaded_objects=tuple(uploaded_objects))


def _upload_with_retries(
    client: S3ClientProtocol,
    item: S3UploadItem,
    *,
    bucket: str,
    max_attempts: int,
    base_delay_seconds: float,
) -> None:
    """Upload one item, retrying transient S3 or network failures."""
    for attempt in range(1, max_attempts + 1):
        try:
            if item.s3_key.startswith("raw/"):
                with item.local_path.open("rb") as stream:
                    client.put_object(
                        Bucket=bucket, Key=item.s3_key, Body=stream, IfNoneMatch="*"
                    )
            else:
                client.upload_file(str(item.local_path), bucket, item.s3_key)
            return
        except Exception as exc:
            if attempt >= max_attempts or not _is_transient_upload_error(exc):
                raise
            if base_delay_seconds > 0:
                time.sleep(base_delay_seconds * attempt)


def _validate_upload_item(item: S3UploadItem) -> None:
    """Validate a local upload source path and destination key."""
    if not item.local_path.is_file():
        raise FileNotFoundError(f"S3 upload source does not exist: {item.local_path}")
    if not item.s3_key or item.s3_key.startswith("/"):
        raise ValueError(f"Invalid S3 key: {item.s3_key}")


def _is_transient_upload_error(exc: Exception) -> bool:
    """Return whether an upload exception is worth retrying."""
    if isinstance(exc, EndpointConnectionError):
        return True
    if isinstance(exc, ClientError):
        code = str(exc.response.get("Error", {}).get("Code", ""))
        return code in TRANSIENT_ERROR_CODES
    return False


def main() -> None:
    """Run the S3 artifact uploader from CLI arguments."""
    parser = argparse.ArgumentParser(description="Upload raw landing artifacts to S3.")
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--manifest-path", action="append", default=[])
    parser.add_argument("--validation-result-path", required=True)
    parser.add_argument("--dbt-artifact-path", action="append", default=[])
    parser.add_argument("--optional", action="store_true")
    args = parser.parse_args()

    summary = upload_run_artifacts_to_s3(
        manifest_paths=args.manifest_path,
        validation_result_path=args.validation_result_path,
        dbt_artifact_paths=args.dbt_artifact_path,
        bucket=args.bucket,
        run_mode="local" if args.optional else "cloud",
    )
    print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
