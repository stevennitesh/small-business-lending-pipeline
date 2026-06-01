"""Discover, download, and manifest SBA 7(a) and 504 FOIA raw files."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO, Sequence
from urllib.parse import urlparse

import requests

from pipelines.extract.extraction_cli import add_common_extraction_arguments
from pipelines.extract.extraction_run import (
    DEFAULT_EXTRACTION_S3_BUCKET,
    ExtractionRun,
    RawManifestSpec,
    build_extraction_run,
    raw_location_for_resource,
    write_raw_extraction_artifact,
)
from pipelines.storage.raw_artifacts import (
    ArtifactLocation,
    LocalArtifactStore,
    LocalRawArtifactStore,
    S3ArtifactStore,
    S3RawArtifactStore,
)
from pipelines.utils.hashing import hash_schema
from pipelines.utils.manifest import ExtractionResult
from pipelines.utils.source_config_models import (
    DEFAULT_SBA_PACKAGE_URL,
    SBA_RESOURCES_CONFIG_FILE,
    SBAResourcesConfig,
    SBAResourceSpec,
    load_sba_resources_config,
)
from pipelines.utils.source_resources import (
    RawSourceResource,
    SBA_FOIA_SOURCE_IDENTITY,
    SourceIdentity,
    sba_raw_source_resource,
)


@dataclass(frozen=True)
class ResolvedSBAResource:
    """SBA package resource matched to a configured logical raw resource."""

    spec: SBAResourceSpec
    source_resource: RawSourceResource
    title: str
    url: str
    file_format: str
    source_size_bytes: int | None = None

    @property
    def filename(self) -> str:
        parsed_name = Path(urlparse(self.url).path).name
        if parsed_name:
            return parsed_name

        extension = self.file_format.lower()
        return f"{self.spec.logical_name}.{extension}"


@dataclass(frozen=True)
class SBAExtractionSummary:
    """Summary returned after SBA FOIA resources are downloaded and manifested."""

    results: dict[str, ExtractionResult]
    manifest_paths: dict[str, Path]
    warnings: list[str]
    manifest_locations: dict[str, ArtifactLocation] = field(default_factory=dict)


@dataclass(frozen=True)
class SBAExtractionInputs:
    """Resolved SBA extraction inputs shared across resource downloads."""

    source_identity: SourceIdentity
    specs: tuple[SBAResourceSpec, ...]
    package_url: str
    package_metadata: dict[str, Any]
    session: requests.Session


def extract_sba_foia(
    *,
    config: SBAResourcesConfig | None = None,
    source_identity: SourceIdentity | None = None,
    specs: list[SBAResourceSpec] | None = None,
    package_metadata: dict[str, Any] | None = None,
    package_url: str | None = None,
    session: requests.Session | None = None,
    data_root: Path | str = "data",
    s3_bucket: str = DEFAULT_EXTRACTION_S3_BUCKET,
    pipeline_run_id: str | None = None,
    extracted_at_utc: str | None = None,
    timeout: int = 120,
    raw_artifact_store: LocalRawArtifactStore | S3RawArtifactStore | None = None,
    manifest_artifact_store: LocalArtifactStore | S3ArtifactStore | None = None,
) -> SBAExtractionSummary:
    """Resolve, download, profile, persist, and manifest configured SBA resources."""
    inputs = _resolve_sba_extraction_inputs(
        config=config,
        source_identity=source_identity,
        specs=specs,
        package_metadata=package_metadata,
        package_url=package_url,
        session=session,
        timeout=timeout,
    )
    resources = resolve_sba_resources(inputs.specs, inputs.package_metadata)
    extraction_run = build_extraction_run(
        data_root=data_root,
        s3_bucket=s3_bucket,
        pipeline_run_id=pipeline_run_id,
        extracted_at_utc=extracted_at_utc,
        raw_artifact_store=raw_artifact_store,
    )

    results: dict[str, ExtractionResult] = {}
    manifest_paths: dict[str, Path] = {}
    manifest_locations: dict[str, ArtifactLocation] = {}
    warnings: list[str] = []

    for logical_name, resource in resources.items():
        try:
            result, manifest_path, manifest_location = _download_resource(
                resource=resource,
                extraction_run=extraction_run,
                inputs=inputs,
                manifest_artifact_store=manifest_artifact_store,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            if _is_data_dictionary(resource):
                warning = (
                    "SBA data dictionary download unavailable for "
                    f"{logical_name}: {exc}"
                )
                warnings.append(warning)
                continue
            raise

        results[logical_name] = result
        manifest_paths[logical_name] = manifest_path
        if manifest_location is not None:
            manifest_locations[logical_name] = manifest_location

    return SBAExtractionSummary(
        results=results,
        manifest_paths=manifest_paths,
        manifest_locations=manifest_locations,
        warnings=warnings,
    )


def fetch_sba_package_metadata(
    package_url: str = DEFAULT_SBA_PACKAGE_URL,
    session: requests.Session | None = None,
    cache_path: Path | str | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    """Fetch SBA open-data package metadata, optionally caching the result."""
    active_session = session or requests.Session()
    response = active_session.get(package_url, timeout=timeout)
    response.raise_for_status()
    payload = response.json()

    if payload.get("success") is False:
        raise ValueError(f"SBA metadata request failed: {payload}")

    metadata = payload.get("result", payload)
    if cache_path is not None:
        resolved_cache_path = Path(cache_path)
        resolved_cache_path.parent.mkdir(parents=True, exist_ok=True)
        resolved_cache_path.write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    return metadata


def resolve_sba_resources(
    specs: Sequence[SBAResourceSpec],
    package_metadata: dict[str, Any],
) -> dict[str, ResolvedSBAResource]:
    """Match configured SBA resource specs to package metadata entries."""
    metadata_resources = package_metadata.get("resources")
    if not isinstance(metadata_resources, list):
        raise ValueError("SBA package metadata must include a resources list")

    resolved: dict[str, ResolvedSBAResource] = {}
    for spec in specs:
        match = _find_resource_match(spec, metadata_resources)
        if match is None:
            if spec.required:
                raise ValueError(
                    f"Could not resolve required SBA resource: {spec.logical_name}"
                )
            continue

        resolved[spec.logical_name] = ResolvedSBAResource(
            spec=spec,
            source_resource=sba_raw_source_resource(
                logical_name=spec.logical_name,
                program=spec.program,
                source_period=spec.source_period,
            ),
            title=str(match.get("name") or match.get("title") or spec.logical_name),
            url=str(match["url"]),
            file_format=str(match.get("format") or spec.expected_format).lower(),
            source_size_bytes=_optional_int(match.get("size")),
        )

    return resolved


def _resolve_sba_extraction_inputs(
    *,
    config: SBAResourcesConfig | None,
    source_identity: SourceIdentity | None,
    specs: list[SBAResourceSpec] | None,
    package_metadata: dict[str, Any] | None,
    package_url: str | None,
    session: requests.Session | None,
    timeout: int,
) -> SBAExtractionInputs:
    """Resolve config, metadata, source identity, specs, and HTTP session."""
    active_session = session or requests.Session()
    active_config = config or (
        None if specs is not None else load_sba_resources_config()
    )
    active_package_url = package_url or (
        active_config.discovery.package_url
        if active_config
        else DEFAULT_SBA_PACKAGE_URL
    )
    metadata = package_metadata or _fetch_or_reject_dynamic_sba_metadata(
        config=active_config,
        package_url=active_package_url,
        session=active_session,
        timeout=timeout,
    )

    return SBAExtractionInputs(
        source_identity=source_identity
        or _default_sba_source_identity(active_config),
        specs=tuple(specs) if specs is not None else active_config.resources,
        package_url=active_package_url,
        package_metadata=metadata,
        session=active_session,
    )


def _default_sba_source_identity(
    config: SBAResourcesConfig | None,
) -> SourceIdentity:
    """Use config dataset naming when config is available."""
    if config is None:
        return SBA_FOIA_SOURCE_IDENTITY
    return SourceIdentity(
        source_system=SBA_FOIA_SOURCE_IDENTITY.source_system,
        dataset_name=config.dataset_name,
    )


def _fetch_or_reject_dynamic_sba_metadata(
    *,
    config: SBAResourcesConfig | None,
    package_url: str,
    session: requests.Session,
    timeout: int,
) -> dict[str, Any]:
    """Fetch package metadata unless config requires caller-supplied metadata."""
    if config is not None and not config.discovery.allow_dynamic_url_resolution:
        raise ValueError(
            "Dynamic SBA resource resolution is disabled; provide package_metadata "
            "or enable discovery.allow_dynamic_url_resolution."
        )

    cache_path = None
    if config is not None and config.discovery.cache_subdir:
        cache_path = Path(config.discovery.cache_subdir) / "sba_package_metadata.json"

    return fetch_sba_package_metadata(
        package_url=package_url,
        session=session,
        cache_path=cache_path,
        timeout=timeout,
    )


def _download_resource(
    *,
    resource: ResolvedSBAResource,
    extraction_run: ExtractionRun,
    inputs: SBAExtractionInputs,
    manifest_artifact_store: LocalArtifactStore | S3ArtifactStore | None,
    timeout: int,
) -> tuple[ExtractionResult, Path, ArtifactLocation | None]:
    """Stream one SBA resource to raw storage and write its manifest."""
    location = raw_location_for_resource(
        extraction_run=extraction_run,
        source_identity=inputs.source_identity,
        source_resource=resource.source_resource,
        filename=resource.filename,
        raw_dataset_name=resource.source_resource.raw_dataset_name,
    )

    response = inputs.session.get(resource.url, timeout=timeout, stream=True)
    response.raise_for_status()

    raw_payload, sha256_checksum, file_size_bytes = _spool_response_payload(response)
    try:
        extraction_run.raw_artifact_store.write_file(location, raw_payload)
        row_count, column_count, schema_hash = _profile_downloaded_payload(
            raw_payload,
            resource.file_format,
            resource.filename,
        )
    finally:
        raw_payload.close()
    artifact = write_raw_extraction_artifact(
        extraction_run=extraction_run,
        spec=RawManifestSpec(
            source_identity=inputs.source_identity,
            resource_name=resource.source_resource.resource_name,
            source_url=resource.url,
            extracted_at_utc=extraction_run.extracted_at_utc,
            ingestion_date=extraction_run.ingestion_date,
            raw_location=location,
            file_format=resource.file_format,
            row_count=row_count,
            sha256_checksum=sha256_checksum,
            schema_hash=schema_hash,
            request_parameters={
                "package_url": inputs.package_url,
                "source_title": resource.title,
                "program": resource.spec.program,
                "source_period": resource.spec.source_period,
            },
            column_count=column_count,
            file_size_bytes=file_size_bytes,
        ),
        manifest_artifact_store=manifest_artifact_store,
    )
    return artifact.result, artifact.manifest_path, artifact.manifest_location


def _spool_response_payload(response: requests.Response) -> tuple[BinaryIO, str, int]:
    """Spool a streamed HTTP response while computing checksum and size."""
    payload = tempfile.SpooledTemporaryFile(max_size=16 * 1024 * 1024)
    hasher = hashlib.sha256()
    file_size_bytes = 0

    try:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if not chunk:
                continue
            hasher.update(chunk)
            file_size_bytes += len(chunk)
            payload.write(chunk)
        payload.seek(0)
    except Exception:
        payload.close()
        raise

    return payload, hasher.hexdigest(), file_size_bytes


def _profile_downloaded_payload(
    payload: BinaryIO,
    file_format: str,
    filename: str,
) -> tuple[int, int | None, str]:
    """Profile downloaded payloads enough to populate manifest row/schema fields."""
    payload.seek(0)
    if file_format == "csv":
        text_stream = io.TextIOWrapper(payload, encoding="utf-8-sig", newline="")
        try:
            reader = csv.reader(text_stream)
            header = next(reader, [])
            row_count = sum(1 for _ in reader)
        finally:
            text_stream.detach()
        schema = [
            {"name": column_name, "ordinal": index}
            for index, column_name in enumerate(header)
        ]
        return row_count, len(header), hash_schema(schema)

    schema = [{"file_format": file_format, "filename": filename}]
    return 0, None, hash_schema(schema)


def _find_resource_match(
    spec: SBAResourceSpec,
    metadata_resources: list[dict[str, Any]],
) -> dict[str, Any] | None:
    expected_format = spec.expected_format.lower()
    for resource in metadata_resources:
        resource_format = str(resource.get("format") or "").lower()
        resource_title = str(resource.get("name") or resource.get("title") or "")
        if resource_format != expected_format:
            continue
        if _title_matches(spec.title_pattern, resource_title):
            return resource
    return None


def _title_matches(pattern: str, title: str) -> bool:
    pattern_tokens = _title_tokens(pattern)
    title_tokens = _title_tokens(title)
    token_index = 0

    for expected_token in pattern_tokens:
        try:
            token_index = title_tokens.index(expected_token, token_index) + 1
        except ValueError:
            return False

    return True


def _title_tokens(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", value.lower())


def _optional_int(value: Any) -> int | None:
    if value in ("", None):
        return None
    return int(value)


def _is_data_dictionary(resource: ResolvedSBAResource) -> bool:
    return resource.spec.logical_name == "sba_foia_data_dictionary"


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract SBA 7(a) and 504 FOIA files.")
    add_common_extraction_arguments(
        parser,
        config_default=f"config/{SBA_RESOURCES_CONFIG_FILE}",
        s3_bucket_default=DEFAULT_EXTRACTION_S3_BUCKET,
    )
    parser.add_argument("--package-url")
    parser.add_argument("--metadata-file")
    args = parser.parse_args()

    metadata = None
    if args.metadata_file:
        metadata = json.loads(Path(args.metadata_file).read_text(encoding="utf-8"))

    summary = extract_sba_foia(
        config=load_sba_resources_config(args.config),
        package_metadata=metadata,
        package_url=args.package_url,
        data_root=args.data_root,
        s3_bucket=args.s3_bucket,
        pipeline_run_id=args.pipeline_run_id,
    )

    for warning in summary.warnings:
        print(f"WARNING: {warning}")
    print(f"Downloaded {len(summary.results)} SBA resources")


if __name__ == "__main__":
    main()
