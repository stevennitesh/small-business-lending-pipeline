"""Compatibility facade for raw artifact storage contracts and implementations."""

from __future__ import annotations

from pipelines.storage.artifact_models import (
    ArtifactLocation,
    ArtifactReference,
    RawArtifactInspection,
    RawArtifactLocation,
    S3ObjectClientProtocol,
    S3RawArtifactReference,
    StorageBackend,
)
from pipelines.storage.artifact_readers import (
    ArtifactReader,
    RawArtifactReader,
    artifact_exists,
    artifact_reader_for_route,
    artifact_uri,
    raw_artifact_reader_for_route,
    read_artifact_text,
)
from pipelines.storage.artifact_stores import (
    LocalArtifactStore,
    LocalRawArtifactStore,
    S3ArtifactStore,
    S3RawArtifactStore,
    artifact_store_for_route,
    raw_artifact_store_for_route,
)
from pipelines.storage.s3_objects import parse_s3_uri


__all__ = [
    "ArtifactLocation",
    "ArtifactReader",
    "ArtifactReference",
    "LocalArtifactStore",
    "LocalRawArtifactStore",
    "RawArtifactInspection",
    "RawArtifactLocation",
    "RawArtifactReader",
    "S3ArtifactStore",
    "S3ObjectClientProtocol",
    "S3RawArtifactReference",
    "S3RawArtifactStore",
    "StorageBackend",
    "artifact_exists",
    "artifact_reader_for_route",
    "artifact_store_for_route",
    "artifact_uri",
    "parse_s3_uri",
    "raw_artifact_reader_for_route",
    "raw_artifact_store_for_route",
    "read_artifact_text",
]
