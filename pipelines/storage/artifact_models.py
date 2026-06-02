from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol


StorageBackend = Literal["local", "s3"]


class S3ObjectClientProtocol(Protocol):
    def put_object(self, *, Bucket: str, Key: str, Body: Any) -> Any: ...

    def get_object(self, *, Bucket: str, Key: str) -> Any: ...


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


@dataclass(frozen=True)
class S3RawArtifactReference:
    bucket: str
    key: str


@dataclass(frozen=True)
class RawArtifactInspection:
    exists: bool
    size_bytes: int
    sha256_checksum: str | None


@dataclass(frozen=True)
class ArtifactLocation:
    storage_backend: StorageBackend
    artifact_uri: str
    artifact_key: str
    local_path: Path | None = None
    s3_uri: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "storage_backend": self.storage_backend,
            "artifact_uri": self.artifact_uri,
            "artifact_key": self.artifact_key,
            "local_path": str(self.local_path) if self.local_path else None,
            "s3_uri": self.s3_uri,
        }


ArtifactReference = Path | str | ArtifactLocation
