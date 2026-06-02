from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol


StorageBackend = Literal["local", "s3"]


class S3ObjectClientProtocol(Protocol):
    """Minimal S3 object client surface used by storage helpers."""

    def put_object(self, *, Bucket: str, Key: str, Body: Any) -> Any:
        """Write one object to an S3 bucket/key."""
        ...

    def get_object(self, *, Bucket: str, Key: str) -> Any:
        """Read one object from an S3 bucket/key."""
        ...


@dataclass(frozen=True)
class RawArtifactLocation:
    """Storage location for immutable raw source artifacts."""

    storage_backend: StorageBackend
    raw_uri: str
    s3_key: str
    local_path: Path | None = None
    s3_uri: str | None = None

    def manifest_fields(self) -> dict[str, str | None]:
        """Return manifest fields that identify where raw data was stored."""
        return {
            "storage_backend": self.storage_backend,
            "raw_uri": self.raw_uri,
            "local_raw_path": str(self.local_path) if self.local_path else None,
            "s3_raw_uri": self.s3_uri,
        }


@dataclass(frozen=True)
class S3RawArtifactReference:
    """Parsed S3 bucket/key reference for a raw or routed artifact."""

    bucket: str
    key: str


@dataclass(frozen=True)
class RawArtifactInspection:
    """Existence, size, and checksum inspection for a raw artifact."""

    exists: bool
    size_bytes: int
    sha256_checksum: str | None


@dataclass(frozen=True)
class ArtifactLocation:
    """Storage location for non-raw artifacts such as manifests or validation."""

    storage_backend: StorageBackend
    artifact_uri: str
    artifact_key: str
    local_path: Path | None = None
    s3_uri: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        """Serialize an artifact location for summaries or manifests."""
        return {
            "storage_backend": self.storage_backend,
            "artifact_uri": self.artifact_uri,
            "artifact_key": self.artifact_key,
            "local_path": str(self.local_path) if self.local_path else None,
            "s3_uri": self.s3_uri,
        }


ArtifactReference = Path | str | ArtifactLocation
