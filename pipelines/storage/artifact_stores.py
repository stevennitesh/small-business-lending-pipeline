from __future__ import annotations

import shutil
from pathlib import Path
from typing import BinaryIO

from pipelines.storage.artifact_models import (
    ArtifactLocation,
    RawArtifactLocation,
    S3ObjectClientProtocol,
    StorageBackend,
)
from pipelines.storage.s3_objects import (
    default_s3_client,
    normalized_s3_bucket,
    put_s3_object,
    read_s3_object,
    require_s3_location,
)
from pipelines.utils.paths import (
    build_local_raw_path,
    build_partitioned_artifact_key,
    build_raw_s3_key,
    build_s3_uri,
)


class LocalRawArtifactStore:
    """Local filesystem store for raw source artifacts."""

    storage_backend: StorageBackend = "local"

    def __init__(self, *, data_root: Path | str = "data", s3_bucket: str | None = None):
        """Create a local raw store rooted under data_root."""
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
        """Return the local raw artifact location for a source/run partition."""
        return _build_raw_artifact_location(
            storage_backend="local",
            data_root=self.data_root,
            s3_bucket=self.s3_bucket,
            source_system=source_system,
            dataset_name=dataset_name,
            resource_name=resource_name,
            ingestion_date=ingestion_date,
            pipeline_run_id=pipeline_run_id,
            filename=filename,
        )

    def write_bytes(self, location: RawArtifactLocation, payload: bytes) -> None:
        """Write raw artifact bytes to a local location."""
        _write_local_bytes(
            location.local_path,
            payload,
            message="Local raw artifact location requires local_path.",
            exclusive=True,
        )

    def write_file(self, location: RawArtifactLocation, payload: BinaryIO) -> None:
        """Stream a file-like raw artifact payload to a local location."""
        _write_local_file(
            location.local_path,
            payload,
            message="Local raw artifact location requires local_path.",
            exclusive=True,
        )

    def read_bytes(self, location: RawArtifactLocation) -> bytes:
        """Read raw artifact bytes from a local location."""
        return _read_local_bytes(
            location.local_path,
            message="Local raw artifact location requires local_path.",
        )


class LocalArtifactStore:
    """Local filesystem store for manifests, validation, and run artifacts."""

    storage_backend: StorageBackend = "local"

    def __init__(self, *, data_root: Path | str = "data", s3_bucket: str | None = None):
        """Create a local non-raw artifact store rooted under data_root."""
        self.data_root = Path(data_root)
        self.s3_bucket = s3_bucket

    def location(
        self,
        *,
        prefix: str,
        source_system: str,
        dataset_name: str,
        resource_name: str,
        ingestion_date: str,
        pipeline_run_id: str,
        filename: str,
    ) -> ArtifactLocation:
        """Return the local artifact location for a source/run partition."""
        return _build_artifact_location(
            storage_backend="local",
            data_root=self.data_root,
            s3_bucket=self.s3_bucket,
            prefix=prefix,
            source_system=source_system,
            dataset_name=dataset_name,
            resource_name=resource_name,
            ingestion_date=ingestion_date,
            pipeline_run_id=pipeline_run_id,
            filename=filename,
        )

    def write_bytes(self, location: ArtifactLocation, payload: bytes) -> None:
        """Write artifact bytes to a local location."""
        _write_local_bytes(
            location.local_path,
            payload,
            message="Local artifact location requires local_path.",
        )

    def read_bytes(self, location: ArtifactLocation) -> bytes:
        """Read artifact bytes from a local location."""
        return _read_local_bytes(
            location.local_path,
            message="Local artifact location requires local_path.",
        )


class S3RawArtifactStore:
    """S3-backed store for raw source artifacts."""

    storage_backend: StorageBackend = "s3"

    def __init__(
        self,
        *,
        bucket: str,
        s3_client: S3ObjectClientProtocol | None = None,
    ):
        """Create an S3 raw artifact store for one bucket."""
        self.bucket = normalized_s3_bucket(
            bucket,
            empty_message="S3 raw artifact bucket cannot be empty.",
        )
        self.s3_client = s3_client or default_s3_client()

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
        """Return the S3 raw artifact location for a source/run partition."""
        return _build_raw_artifact_location(
            storage_backend="s3",
            data_root=None,
            s3_bucket=self.bucket,
            source_system=source_system,
            dataset_name=dataset_name,
            resource_name=resource_name,
            ingestion_date=ingestion_date,
            pipeline_run_id=pipeline_run_id,
            filename=filename,
        )

    def write_bytes(self, location: RawArtifactLocation, payload: bytes) -> None:
        """Write raw artifact bytes to S3."""
        self._require_s3_location(location)
        _write_s3_payload(
            s3_client=self.s3_client,
            bucket=self.bucket,
            key=location.s3_key,
            payload=payload,
            exclusive=True,
        )

    def write_file(self, location: RawArtifactLocation, payload: BinaryIO) -> None:
        """Stream a file-like raw artifact payload to S3."""
        self._require_s3_location(location)
        _write_s3_payload(
            s3_client=self.s3_client,
            bucket=self.bucket,
            key=location.s3_key,
            payload=payload,
            exclusive=True,
        )

    def read_bytes(self, location: RawArtifactLocation) -> bytes:
        """Read raw artifact bytes from S3."""
        self._require_s3_location(location)
        return read_s3_object(
            self.s3_client,
            bucket=self.bucket,
            key=location.s3_key,
        )

    def _require_s3_location(self, location: RawArtifactLocation) -> None:
        """Require a raw artifact location owned by an S3-backed route."""
        require_s3_location(
            location.storage_backend,
            message="S3 raw artifact store requires an S3 location.",
        )


class S3ArtifactStore:
    """S3-backed store for manifests, validation, and run artifacts."""

    storage_backend: StorageBackend = "s3"

    def __init__(
        self,
        *,
        bucket: str,
        s3_client: S3ObjectClientProtocol | None = None,
    ):
        """Create an S3 non-raw artifact store for one bucket."""
        self.bucket = normalized_s3_bucket(
            bucket,
            empty_message="S3 artifact bucket cannot be empty.",
        )
        self.s3_client = s3_client or default_s3_client()

    def location(
        self,
        *,
        prefix: str,
        source_system: str,
        dataset_name: str,
        resource_name: str,
        ingestion_date: str,
        pipeline_run_id: str,
        filename: str,
    ) -> ArtifactLocation:
        """Return the S3 artifact location for a source/run partition."""
        return _build_artifact_location(
            storage_backend="s3",
            data_root=None,
            s3_bucket=self.bucket,
            prefix=prefix,
            source_system=source_system,
            dataset_name=dataset_name,
            resource_name=resource_name,
            ingestion_date=ingestion_date,
            pipeline_run_id=pipeline_run_id,
            filename=filename,
        )

    def write_bytes(self, location: ArtifactLocation, payload: bytes) -> None:
        """Write artifact bytes to S3."""
        self._require_s3_location(location)
        _write_s3_payload(
            s3_client=self.s3_client,
            bucket=self.bucket,
            key=location.artifact_key,
            payload=payload,
        )

    def read_bytes(self, location: ArtifactLocation) -> bytes:
        """Read artifact bytes from S3."""
        self._require_s3_location(location)
        return read_s3_object(
            self.s3_client,
            bucket=self.bucket,
            key=location.artifact_key,
        )

    def _require_s3_location(self, location: ArtifactLocation) -> None:
        """Require an artifact location owned by an S3-backed route."""
        require_s3_location(
            location.storage_backend,
            message="S3 artifact store requires an S3 location.",
        )


def raw_artifact_store_for_route(
    *,
    cloud_route: bool,
    data_root: Path | str = "data",
    bucket: str | None = None,
    s3_client: S3ObjectClientProtocol | None = None,
) -> LocalRawArtifactStore | S3RawArtifactStore:
    """Build the raw artifact store for the local or cloud route."""
    if cloud_route:
        if bucket is None:
            raise ValueError("Cloud raw artifact store requires an S3 bucket.")
        return S3RawArtifactStore(bucket=bucket, s3_client=s3_client)
    return LocalRawArtifactStore(data_root=data_root, s3_bucket=bucket)


def artifact_store_for_route(
    *,
    cloud_route: bool,
    data_root: Path | str = "data",
    bucket: str | None = None,
    s3_client: S3ObjectClientProtocol | None = None,
) -> LocalArtifactStore | S3ArtifactStore:
    """Build the non-raw artifact store for the local or cloud route."""
    if cloud_route:
        if bucket is None:
            raise ValueError("Cloud artifact store requires an S3 bucket.")
        return S3ArtifactStore(bucket=bucket, s3_client=s3_client)
    return LocalArtifactStore(data_root=data_root, s3_bucket=bucket)


def _require_local_path(path: Path | None, message: str) -> Path:
    """Require a local path for a local-backed artifact operation."""
    if path is None:
        raise ValueError(message)
    return path


def _write_local_bytes(
    path: Path | None, payload: bytes, *, message: str, exclusive: bool = False
) -> None:
    """Write bytes to a required local artifact path."""
    local_path = _require_local_path(path, message)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    with local_path.open("xb" if exclusive else "wb") as output_file:
        output_file.write(payload)


def _write_local_file(
    path: Path | None, payload: BinaryIO, *, message: str, exclusive: bool = False
) -> None:
    """Stream a file-like payload into a required local artifact path."""
    local_path = _require_local_path(path, message)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    # Callers often pass a spooled download that was already read for checksums;
    # rewind before copying so the persisted artifact is complete.
    payload.seek(0)
    with local_path.open("xb" if exclusive else "wb") as output_file:
        shutil.copyfileobj(payload, output_file)


def _read_local_bytes(path: Path | None, *, message: str) -> bytes:
    """Read bytes from a required local artifact path."""
    return _require_local_path(path, message).read_bytes()


def _write_s3_payload(
    *,
    s3_client: S3ObjectClientProtocol,
    bucket: str,
    key: str,
    payload: bytes | BinaryIO,
    exclusive: bool = False,
) -> None:
    """Write a bytes or file-like payload to S3."""
    if hasattr(payload, "seek"):
        # Match local write behavior for file-like payloads that were previously
        # consumed by checksum or profiling code.
        payload.seek(0)
    put_s3_object(
        s3_client,
        bucket=bucket,
        key=key,
        body=payload,
        exclusive=exclusive,
    )


def _build_raw_artifact_location(
    *,
    storage_backend: StorageBackend,
    data_root: Path | None,
    s3_bucket: str | None,
    source_system: str,
    dataset_name: str,
    resource_name: str,
    ingestion_date: str,
    pipeline_run_id: str,
    filename: str,
) -> RawArtifactLocation:
    """Build the storage location for an immutable raw source artifact."""
    s3_key = build_raw_s3_key(
        source_system=source_system,
        dataset_name=dataset_name,
        resource_name=resource_name,
        ingestion_date=ingestion_date,
        pipeline_run_id=pipeline_run_id,
        filename=filename,
    )
    s3_uri = build_s3_uri(s3_bucket, s3_key) if s3_bucket else None
    if storage_backend == "local":
        # Local manifests can still carry the eventual S3 URI when a bucket is
        # configured, but raw_uri remains the local file used by DuckDB loads.
        if data_root is None:
            raise ValueError("Local raw artifact location requires data_root.")
        local_path = build_local_raw_path(
            data_root=data_root,
            source_system=source_system,
            dataset_name=dataset_name,
            resource_name=resource_name,
            ingestion_date=ingestion_date,
            pipeline_run_id=pipeline_run_id,
            filename=filename,
        )
        return RawArtifactLocation(
            storage_backend="local",
            raw_uri=str(local_path),
            local_path=local_path,
            s3_uri=s3_uri,
            s3_key=s3_key,
        )
    if s3_uri is None:
        raise ValueError("S3 raw artifact location requires an S3 bucket.")
    return RawArtifactLocation(
        storage_backend="s3",
        raw_uri=s3_uri,
        local_path=None,
        s3_uri=s3_uri,
        s3_key=s3_key,
    )


def _build_artifact_location(
    *,
    storage_backend: StorageBackend,
    data_root: Path | None,
    s3_bucket: str | None,
    prefix: str,
    source_system: str,
    dataset_name: str,
    resource_name: str,
    ingestion_date: str,
    pipeline_run_id: str,
    filename: str,
) -> ArtifactLocation:
    """Build the storage location for routed non-raw artifacts."""
    artifact_key = build_partitioned_artifact_key(
        prefix=prefix,
        source_system=source_system,
        dataset_name=dataset_name,
        resource_name=resource_name,
        ingestion_date=ingestion_date,
        pipeline_run_id=pipeline_run_id,
        filename=filename,
    )
    s3_uri = build_s3_uri(s3_bucket, artifact_key) if s3_bucket else None
    if storage_backend == "local":
        if data_root is None:
            raise ValueError("Local artifact location requires data_root.")
        local_path = data_root / artifact_key
        return ArtifactLocation(
            storage_backend="local",
            artifact_uri=str(local_path),
            artifact_key=artifact_key,
            local_path=local_path,
            s3_uri=s3_uri,
        )
    if s3_uri is None:
        raise ValueError("S3 artifact location requires an S3 bucket.")
    return ArtifactLocation(
        storage_backend="s3",
        artifact_uri=s3_uri,
        artifact_key=artifact_key,
        local_path=None,
        s3_uri=s3_uri,
    )
