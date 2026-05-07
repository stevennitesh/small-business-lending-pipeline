from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

import boto3
from botocore.exceptions import ClientError, EndpointConnectionError

from pipelines.utils.paths import build_raw_s3_key, build_s3_uri


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
    def upload_file(self, filename: str, bucket: str, key: str) -> None:
        ...


@dataclass(frozen=True)
class S3UploadItem:
    local_path: Path
    s3_key: str

    @property
    def s3_category(self) -> str:
        return self.s3_key.split("/", 1)[0]


@dataclass(frozen=True)
class S3UploadSummary:
    bucket: str | None
    uploaded_objects: tuple[str, ...]
    skipped: bool = False
    warning: str | None = None

    @property
    def uploaded_count(self) -> int:
        return len(self.uploaded_objects)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class S3UploadRequiredError(RuntimeError):
    pass


def build_raw_upload_item(manifest: dict[str, Any]) -> S3UploadItem:
    local_path = Path(str(manifest["local_raw_path"]))
    return S3UploadItem(
        local_path=local_path,
        s3_key=build_raw_s3_key(
            source_system=str(manifest["source_system"]),
            dataset_name=str(manifest["dataset_name"]),
            resource_name=str(manifest["resource_name"]),
            ingestion_date=str(manifest["ingestion_date"]),
            pipeline_run_id=str(manifest["pipeline_run_id"]),
            filename=local_path.name,
        ),
    )


def build_manifest_upload_item(
    manifest_path: Path | str,
    manifest: dict[str, Any],
) -> S3UploadItem:
    return S3UploadItem(
        local_path=Path(manifest_path),
        s3_key=_partitioned_artifact_key(
            prefix="manifests",
            manifest=manifest,
            filename=Path(manifest_path).name,
        ),
    )


def build_validation_upload_item(
    validation_path: Path | str,
    manifest: dict[str, Any],
) -> S3UploadItem:
    return S3UploadItem(
        local_path=Path(validation_path),
        s3_key=_partitioned_artifact_key(
            prefix="validation",
            manifest=manifest,
            filename=Path(validation_path).name,
        ),
    )


def build_dbt_artifact_upload_item(
    artifact_path: Path | str,
    *,
    ingestion_date: str,
    pipeline_run_id: str,
) -> S3UploadItem:
    path = Path(artifact_path)
    return S3UploadItem(
        local_path=path,
        s3_key="/".join(
            [
                "validation",
                "dbt",
                "artifacts",
                f"ingestion_date={ingestion_date}",
                f"pipeline_run_id={pipeline_run_id}",
                path.name,
            ]
        ),
    )


def build_run_upload_items(
    *,
    manifest_paths: list[Path | str],
    validation_result_path: Path | str,
    dbt_artifact_paths: list[Path | str] | None = None,
) -> list[S3UploadItem]:
    items: list[S3UploadItem] = []
    manifests: list[dict[str, Any]] = []
    for manifest_path in manifest_paths:
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        manifests.append(manifest)
        items.append(build_raw_upload_item(manifest))
        items.append(build_manifest_upload_item(manifest_path, manifest))
        items.append(build_validation_upload_item(validation_result_path, manifest))

    if dbt_artifact_paths:
        ingestion_date, pipeline_run_id = _single_run_partition(manifests)
        items.extend(
            build_dbt_artifact_upload_item(
                artifact_path,
                ingestion_date=ingestion_date,
                pipeline_run_id=pipeline_run_id,
            )
            for artifact_path in dbt_artifact_paths
        )
    return items


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
    if run_mode not in {"local", "final"}:
        raise ValueError("run_mode must be 'local' or 'final'.")
    return upload_items_to_s3(
        build_run_upload_items(
            manifest_paths=manifest_paths,
            validation_result_path=validation_result_path,
            dbt_artifact_paths=dbt_artifact_paths,
        ),
        bucket=bucket,
        s3_client=s3_client,
        required=run_mode == "final",
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
            message_prefix = "required S3 upload failed" if required else "S3 upload failed"
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
    for attempt in range(1, max_attempts + 1):
        try:
            client.upload_file(str(item.local_path), bucket, item.s3_key)
            return
        except Exception as exc:
            if attempt >= max_attempts or not _is_transient_upload_error(exc):
                raise
            if base_delay_seconds > 0:
                time.sleep(base_delay_seconds * attempt)


def _validate_upload_item(item: S3UploadItem) -> None:
    if not item.local_path.is_file():
        raise FileNotFoundError(f"S3 upload source does not exist: {item.local_path}")
    if not item.s3_key or item.s3_key.startswith("/"):
        raise ValueError(f"Invalid S3 key: {item.s3_key}")


def _is_transient_upload_error(exc: Exception) -> bool:
    if isinstance(exc, EndpointConnectionError):
        return True
    if isinstance(exc, ClientError):
        code = str(exc.response.get("Error", {}).get("Code", ""))
        return code in TRANSIENT_ERROR_CODES
    return False


def _partitioned_artifact_key(
    *,
    prefix: str,
    manifest: dict[str, Any],
    filename: str,
) -> str:
    return "/".join(
        [
            prefix,
            str(manifest["source_system"]),
            str(manifest["dataset_name"]),
            str(manifest["resource_name"]),
            f"ingestion_date={manifest['ingestion_date']}",
            f"pipeline_run_id={manifest['pipeline_run_id']}",
            filename,
        ]
    )


def _single_run_partition(manifests: list[dict[str, Any]]) -> tuple[str, str]:
    partitions = {
        (str(manifest["ingestion_date"]), str(manifest["pipeline_run_id"]))
        for manifest in manifests
    }
    if len(partitions) != 1:
        raise ValueError("dbt artifact uploads require one ingestion_date and pipeline_run_id.")
    return next(iter(partitions))


def main() -> None:
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
        run_mode="local" if args.optional else "final",
    )
    print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
