"""Shared raw validation data models and payload type aliases."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, NotRequired, TypeAlias, TypedDict

from pipelines.storage.raw_artifacts import ArtifactLocation


class RawManifest(TypedDict):
    """Typed shape expected from raw extraction manifest JSON files."""

    pipeline_run_id: str
    source_system: str
    dataset_name: str
    resource_name: str
    source_url: str
    extracted_at_utc: str
    ingestion_date: str
    local_raw_path: str | None
    raw_uri: str | None
    s3_raw_uri: str
    storage_backend: str
    file_format: str
    row_count: int
    sha256_checksum: str
    schema_hash: str
    validation_status: str
    request_parameters: NotRequired[dict[str, Any]]
    column_count: NotRequired[int | None]
    file_size_bytes: NotRequired[int | None]
    validation_messages: NotRequired[list[str]]


JsonPayload: TypeAlias = (
    None
    | bool
    | int
    | float
    | str
    | list["JsonPayload"]
    | dict[str, "JsonPayload"]
)
CensusBdsPayload: TypeAlias = list[list[str]]
BlsLausPayload: TypeAlias = dict[str, JsonPayload]


@dataclass(frozen=True)
class LoadedManifestReference:
    """A loaded manifest paired with its filesystem or artifact-store reference."""

    reference: Path | ArtifactLocation
    manifest: RawManifest


@dataclass(frozen=True)
class RawManifestIndex:
    """Lookup structure for loaded manifests by resource name."""

    manifests: list[RawManifest]
    manifests_by_resource: dict[str, RawManifest]

    @classmethod
    def from_manifests(
        cls,
        manifests: Iterable[RawManifest],
    ) -> "RawManifestIndex":
        manifest_list = list(manifests)
        return cls(
            manifests=manifest_list,
            manifests_by_resource={
                str(manifest["resource_name"]): manifest
                for manifest in manifest_list
            },
        )

    def manifest_for(self, resource_name: str) -> RawManifest:
        """Return one manifest by resource name or raise a validation-friendly error."""
        try:
            return self.manifests_by_resource[resource_name]
        except KeyError as exc:
            raise ValueError(
                f"No manifest found for resource: {resource_name}"
            ) from exc


@dataclass(frozen=True)
class RawValidationInput:
    """Inputs required to run raw validation for one pipeline run."""

    pipeline_run_id: str
    extract_mode: str
    is_cloud_route: bool
    data_root: Path
    run_started_at_utc: str
    validation_path: Path
    manifest_references: tuple[Path | ArtifactLocation, ...]
    s3_bucket: str | None = None


@dataclass(frozen=True)
class RawValidationOutput:
    """Durable reference to the written raw validation result artifact."""

    local_path: Path
    artifact_location: ArtifactLocation | None = None

    @property
    def durable_reference(self) -> Path | ArtifactLocation:
        """Return the cloud artifact location when present, otherwise local path."""
        return self.artifact_location or self.local_path


@dataclass(frozen=True)
class RawValidationExpectations:
    """Resolved source-specific expectations used by raw validation checks."""

    sba_required_resource_names: list[str]
    census_required_variables: tuple[str, ...]
    census_expected_state_count: int
    bls_expected_series_ids: tuple[str, ...]
    bls_required_period_pattern: str
    bls_unemployment_rate_min: float
    bls_unemployment_rate_max: float
