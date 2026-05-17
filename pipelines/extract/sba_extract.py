from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO, Mapping
from urllib.parse import urlparse

import requests

from pipelines.storage.raw_artifacts import (
    ArtifactLocation,
    LocalArtifactStore,
    LocalRawArtifactStore,
    S3ArtifactStore,
    S3RawArtifactStore,
)
from pipelines.utils.config import SourceIdentity, load_yaml_file
from pipelines.utils.dates import (
    format_utc_timestamp,
    ingestion_date_from_timestamp,
    utc_now,
)
from pipelines.utils.hashing import hash_schema
from pipelines.utils.manifest import (
    ExtractionManifest,
    ExtractionResult,
    manifest_to_json_bytes,
    write_manifest,
)


DEFAULT_SBA_PACKAGE_URL = (
    "https://data.sba.gov/api/3/action/package_show?id=7-a-504-foia"
)
DEFAULT_S3_BUCKET = "small-business-lending-pipeline"
DEFAULT_SOURCE_IDENTITY = SourceIdentity(
    source_system="sba",
    dataset_name="7a_504_foia",
)


@dataclass(frozen=True)
class SBAResourceSpec:
    logical_name: str
    program: str
    source_period: str
    expected_format: str
    required: bool
    title_pattern: str


@dataclass(frozen=True)
class SBADiscoveryConfig:
    strategy: str
    package_url: str
    allow_dynamic_url_resolution: bool
    cache_subdir: str | None = None


@dataclass(frozen=True)
class SBAResourcesConfig:
    dataset_name: str
    discovery: SBADiscoveryConfig
    resources: tuple[SBAResourceSpec, ...]


@dataclass(frozen=True)
class ResolvedSBAResource:
    spec: SBAResourceSpec
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

    @property
    def dataset_path_name(self) -> str:
        if self.spec.program == "7a":
            return "7a_foia"
        if self.spec.program == "504":
            return "504_foia"
        return "data_dictionary"

    @property
    def resource_path_name(self) -> str:
        if self.spec.source_period == "all":
            return "all"
        return f"source_period={self.spec.source_period}"


@dataclass(frozen=True)
class SBAExtractionSummary:
    results: dict[str, ExtractionResult]
    manifest_paths: dict[str, Path]
    warnings: list[str]
    manifest_locations: dict[str, ArtifactLocation] = field(default_factory=dict)


def load_sba_resource_specs(
    config_path: Path | str = "config/sba_resources.yml",
) -> list[SBAResourceSpec]:
    return list(load_sba_resources_config(config_path).resources)


def load_sba_resources_config(
    config_path: Path | str = "config/sba_resources.yml",
) -> SBAResourcesConfig:
    return parse_sba_resources_config(
        load_yaml_file(Path(config_path))["sba_resources"]
    )


def parse_sba_resources_config(config: Mapping[str, Any]) -> SBAResourcesConfig:
    discovery = config.get("discovery", {})
    strategy = str(discovery.get("strategy", "sba_open_data_metadata"))
    if strategy != "sba_open_data_metadata":
        raise ValueError(f"Unsupported SBA discovery strategy: {strategy}")

    return SBAResourcesConfig(
        dataset_name=str(config["dataset_name"]),
        discovery=SBADiscoveryConfig(
            strategy=strategy,
            package_url=str(discovery.get("package_url", DEFAULT_SBA_PACKAGE_URL)),
            allow_dynamic_url_resolution=bool(
                discovery.get("allow_dynamic_url_resolution", True)
            ),
            cache_subdir=(
                str(discovery["cache_subdir"])
                if discovery.get("cache_subdir") is not None
                else None
            ),
        ),
        resources=tuple(
            SBAResourceSpec(
                logical_name=str(resource["logical_name"]),
                program=str(resource["program"]),
                source_period=str(resource["source_period"]),
                expected_format=str(resource["expected_format"]).lower(),
                required=bool(resource["required"]),
                title_pattern=str(resource["title_pattern"]),
            )
            for resource in config["resources"]
        ),
    )


def fetch_sba_package_metadata(
    package_url: str = DEFAULT_SBA_PACKAGE_URL,
    session: requests.Session | None = None,
    cache_path: Path | str | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
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
    specs: list[SBAResourceSpec],
    package_metadata: dict[str, Any],
) -> dict[str, ResolvedSBAResource]:
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
            title=str(match.get("name") or match.get("title") or spec.logical_name),
            url=str(match["url"]),
            file_format=str(match.get("format") or spec.expected_format).lower(),
            source_size_bytes=_optional_int(match.get("size")),
        )

    return resolved


def extract_sba_foia(
    *,
    config: SBAResourcesConfig | None = None,
    source_identity: SourceIdentity | None = None,
    specs: list[SBAResourceSpec] | None = None,
    package_metadata: dict[str, Any] | None = None,
    package_url: str | None = None,
    session: requests.Session | None = None,
    data_root: Path | str = "data",
    s3_bucket: str = DEFAULT_S3_BUCKET,
    pipeline_run_id: str | None = None,
    extracted_at_utc: str | None = None,
    timeout: int = 120,
    raw_artifact_store: LocalRawArtifactStore | S3RawArtifactStore | None = None,
    manifest_artifact_store: LocalArtifactStore | S3ArtifactStore | None = None,
) -> SBAExtractionSummary:
    active_session = session or requests.Session()
    active_config = config or (
        None if specs is not None else load_sba_resources_config()
    )
    active_identity = source_identity or (
        SourceIdentity(
            source_system=DEFAULT_SOURCE_IDENTITY.source_system,
            dataset_name=active_config.dataset_name,
        )
        if active_config
        else DEFAULT_SOURCE_IDENTITY
    )
    active_specs = tuple(specs) if specs is not None else active_config.resources
    active_package_url = package_url or (
        active_config.discovery.package_url if active_config else DEFAULT_SBA_PACKAGE_URL
    )
    metadata = package_metadata or _fetch_or_reject_dynamic_sba_metadata(
        config=active_config,
        package_url=active_package_url,
        session=active_session,
        timeout=timeout,
    )
    resources = resolve_sba_resources(active_specs, metadata)
    run_id = pipeline_run_id or str(uuid.uuid4())
    extracted_timestamp = extracted_at_utc or format_utc_timestamp(utc_now())
    ingestion_date = _ingestion_date_from_iso(extracted_timestamp)
    store = raw_artifact_store or LocalRawArtifactStore(
        data_root=Path(data_root),
        s3_bucket=s3_bucket,
    )

    results: dict[str, ExtractionResult] = {}
    manifest_paths: dict[str, Path] = {}
    manifest_locations: dict[str, ArtifactLocation] = {}
    warnings: list[str] = []

    for logical_name, resource in resources.items():
        try:
            result, manifest_path = _download_resource(
                resource=resource,
                source_identity=active_identity,
                session=active_session,
                data_root=Path(data_root),
                raw_artifact_store=store,
                manifest_artifact_store=manifest_artifact_store,
                package_url=active_package_url,
                pipeline_run_id=run_id,
                extracted_at_utc=extracted_timestamp,
                ingestion_date=ingestion_date,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            if _is_data_dictionary(resource):
                warnings.append(
                    f"SBA data dictionary download unavailable for {logical_name}: {exc}"
                )
                continue
            raise

        results[logical_name] = result
        manifest_paths[logical_name] = manifest_path
        if manifest_artifact_store is not None:
            manifest_locations[logical_name] = _manifest_artifact_location(
                manifest_artifact_store,
                manifest=result.manifest,
                filename=manifest_path.name,
            )

    return SBAExtractionSummary(
        results=results,
        manifest_paths=manifest_paths,
        manifest_locations=manifest_locations,
        warnings=warnings,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract SBA 7(a) and 504 FOIA files.")
    parser.add_argument("--config", default="config/sba_resources.yml")
    parser.add_argument("--package-url")
    parser.add_argument("--metadata-file")
    parser.add_argument("--data-root", default="data")
    parser.add_argument("--s3-bucket", default=DEFAULT_S3_BUCKET)
    parser.add_argument("--pipeline-run-id")
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


def _fetch_or_reject_dynamic_sba_metadata(
    *,
    config: SBAResourcesConfig | None,
    package_url: str,
    session: requests.Session,
    timeout: int,
) -> dict[str, Any]:
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
    source_identity: SourceIdentity,
    session: requests.Session,
    data_root: Path,
    raw_artifact_store: LocalRawArtifactStore | S3RawArtifactStore,
    manifest_artifact_store: LocalArtifactStore | S3ArtifactStore | None,
    package_url: str,
    pipeline_run_id: str,
    extracted_at_utc: str,
    ingestion_date: str,
    timeout: int,
) -> tuple[ExtractionResult, Path]:
    location = raw_artifact_store.location(
        source_system=source_identity.source_system,
        dataset_name=resource.dataset_path_name,
        resource_name=resource.resource_path_name,
        ingestion_date=ingestion_date,
        pipeline_run_id=pipeline_run_id,
        filename=resource.filename,
    )

    response = session.get(resource.url, timeout=timeout, stream=True)
    response.raise_for_status()

    raw_payload, sha256_checksum, file_size_bytes = _spool_response_payload(response)
    try:
        raw_artifact_store.write_file(location, raw_payload)
        row_count, column_count, schema_hash = _profile_downloaded_payload(
            raw_payload,
            resource.file_format,
            resource.filename,
        )
    finally:
        raw_payload.close()
    manifest_fields = location.manifest_fields()
    manifest = ExtractionManifest(
        pipeline_run_id=pipeline_run_id,
        source_system=source_identity.source_system,
        dataset_name=source_identity.dataset_name,
        resource_name=resource.spec.logical_name,
        source_url=resource.url,
        extracted_at_utc=extracted_at_utc,
        ingestion_date=ingestion_date,
        local_raw_path=manifest_fields["local_raw_path"],
        s3_raw_uri=str(manifest_fields["s3_raw_uri"]),
        file_format=resource.file_format,
        row_count=row_count,
        sha256_checksum=sha256_checksum,
        schema_hash=schema_hash,
        validation_status="passed",
        raw_uri=str(manifest_fields["raw_uri"]),
        storage_backend=str(manifest_fields["storage_backend"]),
        request_parameters={
            "package_url": package_url,
            "source_title": resource.title,
            "program": resource.spec.program,
            "source_period": resource.spec.source_period,
        },
        column_count=column_count,
        file_size_bytes=file_size_bytes,
        validation_messages=[],
    )
    manifest_path = _build_local_manifest_path(
        data_root=data_root,
        ingestion_date=ingestion_date,
        pipeline_run_id=pipeline_run_id,
        logical_name=resource.spec.logical_name,
    )
    write_manifest(manifest, manifest_path)
    if manifest_artifact_store is not None:
        manifest_location = _manifest_artifact_location(
            manifest_artifact_store,
            manifest=manifest,
            filename=manifest_path.name,
        )
        manifest_artifact_store.write_bytes(
            manifest_location,
            manifest_to_json_bytes(manifest),
        )

    return (
        ExtractionResult(
            manifest=manifest,
            local_raw_path=location.local_path,
            row_count=row_count,
        ),
        manifest_path,
    )


def _manifest_artifact_location(
    manifest_artifact_store: LocalArtifactStore | S3ArtifactStore,
    *,
    manifest: ExtractionManifest,
    filename: str,
) -> ArtifactLocation:
    return manifest_artifact_store.location(
        prefix="manifests",
        source_system=manifest.source_system,
        dataset_name=manifest.dataset_name,
        resource_name=manifest.resource_name,
        ingestion_date=manifest.ingestion_date,
        pipeline_run_id=manifest.pipeline_run_id,
        filename=filename,
    )


def _spool_response_payload(response: requests.Response) -> tuple[BinaryIO, str, int]:
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


def _build_local_manifest_path(
    *,
    data_root: Path,
    ingestion_date: str,
    pipeline_run_id: str,
    logical_name: str,
) -> Path:
    return (
        data_root
        / "manifests"
        / "sba"
        / f"ingestion_date={ingestion_date}"
        / f"pipeline_run_id={pipeline_run_id}"
        / f"{logical_name}.manifest.json"
    )


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


def _ingestion_date_from_iso(value: str) -> str:
    from datetime import datetime

    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return ingestion_date_from_timestamp(timestamp)


if __name__ == "__main__":
    main()
