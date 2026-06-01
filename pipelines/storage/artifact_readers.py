from __future__ import annotations

from pathlib import Path
from typing import Any

from botocore.exceptions import ClientError

from pipelines.storage.artifact_models import (
    ArtifactLocation,
    ArtifactReference,
    RawArtifactInspection,
    S3ObjectClientProtocol,
)
from pipelines.storage.s3_objects import (
    default_s3_client,
    parse_s3_uri,
    read_s3_object,
)
from pipelines.utils.hashing import hash_bytes


class RawArtifactReader:
    def __init__(self, *, s3_client: S3ObjectClientProtocol | None = None):
        self.s3_client = s3_client

    def inspect(self, manifest: dict[str, Any]) -> RawArtifactInspection:
        try:
            payload = self.read_bytes(manifest)
        except (ClientError, FileNotFoundError) as exc:
            if not _is_missing_artifact_error(exc):
                raise
            return RawArtifactInspection(
                exists=False,
                size_bytes=0,
                sha256_checksum=None,
            )
        return RawArtifactInspection(
            exists=True,
            size_bytes=len(payload),
            sha256_checksum=hash_bytes(payload),
        )

    def exists(self, manifest: dict[str, Any]) -> bool:
        return self.inspect(manifest).exists

    def size_bytes(self, manifest: dict[str, Any]) -> int:
        return self.inspect(manifest).size_bytes

    def sha256(self, manifest: dict[str, Any]) -> str | None:
        return self.inspect(manifest).sha256_checksum

    def read_text(self, manifest: dict[str, Any], encoding: str = "utf-8") -> str:
        return self.read_bytes(manifest).decode(encoding)

    def read_bytes(self, manifest: dict[str, Any]) -> bytes:
        storage_backend = str(manifest.get("storage_backend", "local")).lower()
        if storage_backend == "s3":
            raw_uri = str(manifest.get("raw_uri") or manifest["s3_raw_uri"])
            reference = parse_s3_uri(raw_uri)
            client = self.s3_client or default_s3_client()
            return read_s3_object(client, bucket=reference.bucket, key=reference.key)

        local_raw_path = manifest.get("local_raw_path")
        if local_raw_path:
            return Path(str(local_raw_path)).read_bytes()
        raise FileNotFoundError("Manifest does not include local_raw_path.")


class ArtifactReader:
    def __init__(self, *, s3_client: S3ObjectClientProtocol | None = None):
        self.s3_client = s3_client

    def exists(self, location: ArtifactLocation) -> bool:
        try:
            self.read_bytes(location)
        except (ClientError, FileNotFoundError) as exc:
            if not _is_missing_artifact_error(exc):
                raise
            return False
        return True

    def read_text(self, location: ArtifactLocation, encoding: str = "utf-8") -> str:
        return self.read_bytes(location).decode(encoding)

    def read_bytes(self, location: ArtifactLocation) -> bytes:
        if location.storage_backend == "s3":
            reference = parse_s3_uri(location.s3_uri or location.artifact_uri)
            client = self.s3_client or default_s3_client()
            return read_s3_object(client, bucket=reference.bucket, key=reference.key)

        if location.local_path:
            return location.local_path.read_bytes()
        raise FileNotFoundError("Local artifact location requires local_path.")


def read_artifact_text(
    reference: ArtifactReference,
    artifact_reader: ArtifactReader,
) -> str:
    if isinstance(reference, ArtifactLocation):
        return artifact_reader.read_text(reference)
    return Path(reference).read_text(encoding="utf-8")


def artifact_exists(
    reference: ArtifactReference,
    artifact_reader: ArtifactReader,
) -> bool:
    if isinstance(reference, ArtifactLocation):
        return artifact_reader.exists(reference)
    return Path(reference).is_file()


def artifact_uri(reference: ArtifactReference) -> str:
    if isinstance(reference, ArtifactLocation):
        return reference.artifact_uri
    return str(reference)


def _is_missing_artifact_error(exc: ClientError | FileNotFoundError) -> bool:
    if isinstance(exc, FileNotFoundError):
        return True
    error_code = str(exc.response.get("Error", {}).get("Code", ""))
    return error_code in {"404", "NoSuchKey", "NotFound", "NotFoundException"}


def raw_artifact_reader_for_route(
    *,
    cloud_route: bool,
    s3_client: S3ObjectClientProtocol | None = None,
) -> RawArtifactReader:
    return RawArtifactReader(s3_client=s3_client if cloud_route else None)


def artifact_reader_for_route(
    *,
    cloud_route: bool,
    s3_client: S3ObjectClientProtocol | None = None,
) -> ArtifactReader:
    return ArtifactReader(s3_client=s3_client if cloud_route else None)
