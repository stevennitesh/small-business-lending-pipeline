"""Shared run context and artifact writers for source extraction modules."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

from pipelines.storage.raw_artifacts import (
    ArtifactLocation,
    LocalArtifactStore,
    LocalRawArtifactStore,
    RawArtifactLocation,
    S3ArtifactStore,
    S3RawArtifactStore,
)
from pipelines.utils.dates import (
    format_utc_timestamp,
    ingestion_date_from_iso_timestamp,
    utc_now,
)
from pipelines.utils.hashing import hash_bytes, hash_schema
from pipelines.utils.manifest import (
    ExtractionManifest,
    ExtractionResult,
    write_extraction_manifest_outputs,
    write_manifest_outputs,
)
from pipelines.utils.source_resources import RawSourceResource, SourceIdentity


DEFAULT_EXTRACTION_S3_BUCKET = "small-business-lending-pipeline"


@dataclass(frozen=True)
class ExtractionRun:
    """Resolved run context shared by raw payload and manifest writers."""

    data_root: Path
    s3_bucket: str
    pipeline_run_id: str
    extracted_at_utc: str
    ingestion_date: str
    raw_artifact_store: LocalRawArtifactStore | S3RawArtifactStore


@dataclass(frozen=True)
class WrittenExtractionArtifact:
    """Result bundle returned after raw and manifest artifacts are written."""

    result: ExtractionResult
    manifest_path: Path
    manifest_location: ArtifactLocation | None = None


class SingleResourceExtractionSummary:
    """Mixin for extractors that emit one raw resource manifest."""

    source_resource: ClassVar[RawSourceResource]
    manifest_path: Path
    manifest_location: ArtifactLocation | None

    @property
    def manifest_paths(self) -> dict[str, Path]:
        return {self.source_resource.resource_name: self.manifest_path}

    @property
    def manifest_locations(self) -> dict[str, ArtifactLocation]:
        if self.manifest_location is None:
            return {}
        return {self.source_resource.resource_name: self.manifest_location}


@dataclass(frozen=True)
class JsonExtractionArtifactSpec:
    """Inputs needed to persist a JSON raw extract and its manifest."""

    source_resource: RawSourceResource
    source_url: str
    raw_filename: str
    raw_payload: Any
    row_count: int
    schema_fields: Any
    request_parameters: dict[str, Any]
    source_identity: SourceIdentity | None = None
    manifest_payload_extras: dict[str, Any] | None = None


def resolve_year_range(
    *,
    default_start_year: int,
    start_year: int | None = None,
    end_year: int | None = None,
) -> tuple[int, int]:
    """Resolve optional inclusive year bounds against a source default."""
    return start_year or default_start_year, end_year or datetime.now().year


def resolve_api_key(
    explicit_api_key: str | None,
    *,
    env_var: str,
) -> str | None:
    """Use an explicit API key first, then the source-specific environment key."""
    return explicit_api_key or os.getenv(env_var) or None


def raw_location_for_resource(
    *,
    extraction_run: ExtractionRun,
    source_resource: RawSourceResource,
    filename: str,
    source_identity: SourceIdentity | None = None,
    raw_dataset_name: str | None = None,
) -> RawArtifactLocation:
    """Build the raw storage location from canonical source resource metadata."""
    resolved_source_identity = source_identity or source_resource.source_identity
    return extraction_run.raw_artifact_store.location(
        source_system=resolved_source_identity.source_system,
        dataset_name=raw_dataset_name or resolved_source_identity.dataset_name,
        resource_name=source_resource.raw_resource_name,
        ingestion_date=extraction_run.ingestion_date,
        pipeline_run_id=extraction_run.pipeline_run_id,
        filename=filename,
    )


@dataclass(frozen=True)
class RawManifestSpec:
    """Manifest inputs for an already-written raw extraction artifact."""

    source_identity: SourceIdentity
    resource_name: str
    source_url: str
    extracted_at_utc: str
    ingestion_date: str
    raw_location: RawArtifactLocation
    file_format: str
    row_count: int
    sha256_checksum: str
    schema_hash: str
    request_parameters: dict[str, Any]
    column_count: int | None
    file_size_bytes: int | None
    validation_messages: tuple[str, ...] = ()
    manifest_payload_extras: dict[str, Any] | None = None

    @classmethod
    def from_payload(
        cls,
        *,
        source_identity: SourceIdentity,
        resource_name: str,
        source_url: str,
        extracted_at_utc: str,
        ingestion_date: str,
        raw_location: RawArtifactLocation,
        raw_payload: bytes,
        row_count: int,
        file_format: str,
        schema_fields: Any,
        request_parameters: dict[str, Any],
        validation_messages: tuple[str, ...] = (),
        manifest_payload_extras: dict[str, Any] | None = None,
    ) -> "RawManifestSpec":
        return cls(
            source_identity=source_identity,
            resource_name=resource_name,
            source_url=source_url,
            extracted_at_utc=extracted_at_utc,
            ingestion_date=ingestion_date,
            raw_location=raw_location,
            file_format=file_format,
            row_count=row_count,
            sha256_checksum=hash_bytes(raw_payload),
            schema_hash=hash_schema(schema_fields),
            request_parameters=request_parameters,
            column_count=len(schema_fields),
            file_size_bytes=len(raw_payload),
            validation_messages=validation_messages,
            manifest_payload_extras=manifest_payload_extras,
        )

    @classmethod
    def from_extraction_payload(
        cls,
        *,
        extraction_run: ExtractionRun,
        source_resource: RawSourceResource,
        source_url: str,
        raw_location: RawArtifactLocation,
        raw_payload: bytes,
        row_count: int,
        file_format: str,
        schema_fields: Any,
        request_parameters: dict[str, Any],
        source_identity: SourceIdentity | None = None,
        validation_messages: tuple[str, ...] = (),
        manifest_payload_extras: dict[str, Any] | None = None,
    ) -> "RawManifestSpec":
        resolved_source_identity = source_identity or source_resource.source_identity
        return cls.from_payload(
            source_identity=resolved_source_identity,
            resource_name=source_resource.resource_name,
            source_url=source_url,
            extracted_at_utc=extraction_run.extracted_at_utc,
            ingestion_date=extraction_run.ingestion_date,
            raw_location=raw_location,
            raw_payload=raw_payload,
            row_count=row_count,
            file_format=file_format,
            schema_fields=schema_fields,
            request_parameters=request_parameters,
            validation_messages=validation_messages,
            manifest_payload_extras=manifest_payload_extras,
        )


def build_extraction_run(
    *,
    data_root: Path | str,
    s3_bucket: str,
    pipeline_run_id: str | None = None,
    extracted_at_utc: str | None = None,
    raw_artifact_store: LocalRawArtifactStore | S3RawArtifactStore | None = None,
) -> ExtractionRun:
    """Resolve run IDs, timestamps, ingestion dates, and raw artifact storage."""
    resolved_data_root = Path(data_root)
    resolved_pipeline_run_id = pipeline_run_id or str(uuid.uuid4())
    resolved_extracted_at_utc = extracted_at_utc or format_utc_timestamp(utc_now())
    return ExtractionRun(
        data_root=resolved_data_root,
        s3_bucket=s3_bucket,
        pipeline_run_id=resolved_pipeline_run_id,
        extracted_at_utc=resolved_extracted_at_utc,
        ingestion_date=ingestion_date_from_iso_timestamp(resolved_extracted_at_utc),
        raw_artifact_store=raw_artifact_store
        or LocalRawArtifactStore(
            data_root=resolved_data_root,
            s3_bucket=s3_bucket,
        ),
    )


def _build_raw_manifest(
    *,
    pipeline_run_id: str,
    spec: RawManifestSpec,
) -> ExtractionManifest:
    manifest_fields = spec.raw_location.manifest_fields()
    return ExtractionManifest(
        pipeline_run_id=pipeline_run_id,
        source_system=spec.source_identity.source_system,
        dataset_name=spec.source_identity.dataset_name,
        resource_name=spec.resource_name,
        source_url=spec.source_url,
        extracted_at_utc=spec.extracted_at_utc,
        ingestion_date=spec.ingestion_date,
        local_raw_path=manifest_fields["local_raw_path"],
        s3_raw_uri=manifest_fields["s3_raw_uri"],
        file_format=spec.file_format,
        row_count=spec.row_count,
        sha256_checksum=spec.sha256_checksum,
        schema_hash=spec.schema_hash,
        validation_status="passed",
        request_parameters=spec.request_parameters,
        column_count=spec.column_count,
        file_size_bytes=spec.file_size_bytes,
        validation_messages=list(spec.validation_messages),
        storage_backend=manifest_fields["storage_backend"],
        raw_uri=manifest_fields["raw_uri"],
    )


def _write_raw_manifest(
    *,
    pipeline_run_id: str,
    spec: RawManifestSpec,
    manifest_artifact_store: LocalArtifactStore | S3ArtifactStore | None = None,
    manifest_path: Path | None = None,
    data_root: Path | None = None,
    source_directory: str | None = None,
    filename: str | None = None,
) -> WrittenExtractionArtifact:
    manifest = _build_raw_manifest(
        pipeline_run_id=pipeline_run_id,
        spec=spec,
    )
    manifest_payload = None
    if spec.manifest_payload_extras:
        manifest_payload = {
            **manifest.to_dict(),
            **spec.manifest_payload_extras,
        }
    if manifest_path is not None:
        manifest_output = write_manifest_outputs(
            manifest=manifest,
            manifest_path=manifest_path,
            manifest_artifact_store=manifest_artifact_store,
            manifest_payload=manifest_payload,
        )
    else:
        if data_root is None or source_directory is None or filename is None:
            raise ValueError(
                "data_root, source_directory, and filename are required "
                "when manifest_path is not provided."
            )
        manifest_output = write_extraction_manifest_outputs(
            data_root=data_root,
            source_directory=source_directory,
            manifest=manifest,
            filename=filename,
            manifest_artifact_store=manifest_artifact_store,
            manifest_payload=manifest_payload,
        )

    return WrittenExtractionArtifact(
        result=ExtractionResult(
            manifest=manifest,
            local_raw_path=spec.raw_location.local_path,
            row_count=spec.row_count,
        ),
        manifest_path=manifest_output.manifest_path,
        manifest_location=manifest_output.manifest_location,
    )


def write_raw_extraction_artifact(
    *,
    extraction_run: ExtractionRun,
    spec: RawManifestSpec,
    manifest_artifact_store: LocalArtifactStore | S3ArtifactStore | None = None,
    manifest_path: Path | None = None,
) -> WrittenExtractionArtifact:
    """Write the manifest for a raw artifact that the caller already persisted."""
    return _write_raw_manifest(
        pipeline_run_id=extraction_run.pipeline_run_id,
        spec=spec,
        manifest_path=manifest_path,
        data_root=extraction_run.data_root,
        source_directory=spec.source_identity.source_system,
        filename=f"{spec.resource_name}.manifest.json",
        manifest_artifact_store=manifest_artifact_store,
    )


def write_json_extraction_artifact(
    *,
    extraction_run: ExtractionRun,
    spec: JsonExtractionArtifactSpec,
    manifest_artifact_store: LocalArtifactStore | S3ArtifactStore | None = None,
) -> WrittenExtractionArtifact:
    """Write a JSON raw payload, then write the matching extraction manifest."""
    location = raw_location_for_resource(
        extraction_run=extraction_run,
        source_resource=spec.source_resource,
        filename=spec.raw_filename,
        source_identity=spec.source_identity,
    )
    raw_payload_bytes = (json.dumps(spec.raw_payload, indent=2) + "\n").encode(
        "utf-8"
    )
    extraction_run.raw_artifact_store.write_bytes(location, raw_payload_bytes)
    return write_raw_extraction_artifact(
        extraction_run=extraction_run,
        spec=RawManifestSpec.from_extraction_payload(
            extraction_run=extraction_run,
            source_resource=spec.source_resource,
            source_url=spec.source_url,
            raw_location=location,
            raw_payload=raw_payload_bytes,
            file_format="json",
            row_count=spec.row_count,
            schema_fields=spec.schema_fields,
            request_parameters=spec.request_parameters,
            source_identity=spec.source_identity,
            manifest_payload_extras=spec.manifest_payload_extras,
        ),
        manifest_artifact_store=manifest_artifact_store,
    )
