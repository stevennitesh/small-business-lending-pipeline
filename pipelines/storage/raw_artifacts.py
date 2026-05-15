from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

from pipelines.utils.paths import build_local_raw_path, build_raw_s3_key, build_s3_uri


StorageBackend = Literal["local", "s3"]


class S3ObjectClientProtocol(Protocol):
    def put_object(self, *, Bucket: str, Key: str, Body: bytes) -> Any:
        ...

    def get_object(self, *, Bucket: str, Key: str) -> Any:
        ...


@dataclass(frozen=True)
class RawArtifactLocation:
    storage_backend: StorageBackend
    raw_uri: str
    s3_key: str
    local_path: Path | None = None
    s3_uri: str | None = None

    def manifest_fields(self) -> dict[str, str | None]:
        return {
            "storage_backend": self.storage_backend,
            "raw_uri": self.raw_uri,
            "local_raw_path": str(self.local_path) if self.local_path else None,
            "s3_raw_uri": self.s3_uri,
        }


class LocalRawArtifactStore:
    storage_backend: StorageBackend = "local"

    def __init__(self, *, data_root: Path | str = "data", s3_bucket: str | None = None):
        self.data_root = Path(data_root)
        self.s3_bucket = s3_bucket

    def location(
        self,
        *,
        source_system: str,
        dataset_name: str,
        resource_name: str,
        ingestion_date: str,
        pipeline_run_id: str,
        filename: str,
    ) -> RawArtifactLocation:
        s3_key = build_raw_s3_key(
            source_system=source_system,
            dataset_name=dataset_name,
            resource_name=resource_name,
            ingestion_date=ingestion_date,
            pipeline_run_id=pipeline_run_id,
            filename=filename,
        )
        local_path = build_local_raw_path(
            data_root=self.data_root,
            source_system=source_system,
            dataset_name=dataset_name,
            resource_name=resource_name,
            ingestion_date=ingestion_date,
            pipeline_run_id=pipeline_run_id,
            filename=filename,
        )
        s3_uri = build_s3_uri(self.s3_bucket, s3_key) if self.s3_bucket else None
        return RawArtifactLocation(
            storage_backend="local",
            raw_uri=str(local_path),
            local_path=local_path,
            s3_uri=s3_uri,
            s3_key=s3_key,
        )

    def write_bytes(self, location: RawArtifactLocation, payload: bytes) -> None:
        if location.local_path is None:
            raise ValueError("Local raw artifact location requires local_path.")
        location.local_path.parent.mkdir(parents=True, exist_ok=True)
        location.local_path.write_bytes(payload)

    def read_bytes(self, location: RawArtifactLocation) -> bytes:
        if location.local_path is None:
            raise ValueError("Local raw artifact location requires local_path.")
        return location.local_path.read_bytes()


class S3RawArtifactStore:
    storage_backend: StorageBackend = "s3"

    def __init__(
        self,
        *,
        bucket: str,
        s3_client: S3ObjectClientProtocol | None = None,
    ):
        self.bucket = bucket.removeprefix("s3://").strip("/")
        if not self.bucket:
            raise ValueError("S3 raw artifact bucket cannot be empty.")
        self.s3_client = s3_client or _default_s3_client()

    def location(
        self,
        *,
        source_system: str,
        dataset_name: str,
        resource_name: str,
        ingestion_date: str,
        pipeline_run_id: str,
        filename: str,
    ) -> RawArtifactLocation:
        s3_key = build_raw_s3_key(
            source_system=source_system,
            dataset_name=dataset_name,
            resource_name=resource_name,
            ingestion_date=ingestion_date,
            pipeline_run_id=pipeline_run_id,
            filename=filename,
        )
        s3_uri = build_s3_uri(self.bucket, s3_key)
        return RawArtifactLocation(
            storage_backend="s3",
            raw_uri=s3_uri,
            local_path=None,
            s3_uri=s3_uri,
            s3_key=s3_key,
        )

    def write_bytes(self, location: RawArtifactLocation, payload: bytes) -> None:
        self._require_s3_location(location)
        self.s3_client.put_object(
            Bucket=self.bucket,
            Key=location.s3_key,
            Body=payload,
        )

    def read_bytes(self, location: RawArtifactLocation) -> bytes:
        self._require_s3_location(location)
        response = self.s3_client.get_object(Bucket=self.bucket, Key=location.s3_key)
        return response["Body"].read()

    def _require_s3_location(self, location: RawArtifactLocation) -> None:
        if location.storage_backend != "s3":
            raise ValueError("S3 raw artifact store requires an S3 location.")


def _default_s3_client():
    import boto3

    return boto3.client("s3")
