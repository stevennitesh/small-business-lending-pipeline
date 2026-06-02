from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


REQUIRED_MANIFEST_FIELDS = frozenset(
    {
        "pipeline_run_id",
        "source_system",
        "dataset_name",
        "resource_name",
        "source_url",
        "extracted_at_utc",
        "ingestion_date",
        "local_raw_path",
        "raw_uri",
        "s3_raw_uri",
        "storage_backend",
        "file_format",
        "row_count",
        "sha256_checksum",
        "schema_hash",
        "validation_status",
    }
)

VALIDATION_STATUSES = frozenset({"passed", "warning", "failed"})


@dataclass(frozen=True)
class ExtractionManifest:
    """Manifest describing one extracted raw artifact and its validation state."""

    pipeline_run_id: str
    source_system: str
    dataset_name: str
    resource_name: str
    source_url: str
    extracted_at_utc: str
    ingestion_date: str
    local_raw_path: str | None
    s3_raw_uri: str
    file_format: str
    row_count: int
    sha256_checksum: str
    schema_hash: str
    validation_status: str
    raw_uri: str | None = None
    storage_backend: str = "local"
    request_parameters: dict[str, Any] = field(default_factory=dict)
    column_count: int | None = None
    file_size_bytes: int | None = None
    validation_messages: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize and validate the extraction manifest."""
        return validate_manifest(asdict(self))


@dataclass(frozen=True)
class ExtractionResult:
    """Extraction output plus its manifest and local raw path, when present."""

    manifest: ExtractionManifest
    local_raw_path: Path | None
    row_count: int

    def to_dict(self) -> dict[str, Any]:
        """Serialize an extraction result for summaries."""
        return {
            "manifest": self.manifest.to_dict(),
            "local_raw_path": str(self.local_raw_path) if self.local_raw_path else None,
            "row_count": self.row_count,
        }


@dataclass(frozen=True)
class ManifestWriteResult:
    """Paths and optional routed location written for a manifest."""

    manifest_path: Path
    manifest_location: Any | None = None


def validate_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a raw extraction manifest payload."""
    manifest = normalize_manifest_storage_fields(manifest)
    missing_fields = sorted(REQUIRED_MANIFEST_FIELDS - set(manifest))
    if missing_fields:
        raise ValueError(
            "Missing required manifest fields: " + ", ".join(missing_fields)
        )

    blank_fields = sorted(
        field_name
        for field_name in REQUIRED_MANIFEST_FIELDS
        if _is_blank_required_field(manifest, field_name)
    )
    if blank_fields:
        raise ValueError("Blank required manifest fields: " + ", ".join(blank_fields))

    # Manifests are audit records, so timestamp/date/row-count fields are
    # validated before downstream loaders trust them for partitioning and checks.
    _validate_utc_timestamp(str(manifest["extracted_at_utc"]))
    _validate_ingestion_date(str(manifest["ingestion_date"]))
    _validate_non_negative_int("row_count", manifest["row_count"])

    validation_status = str(manifest["validation_status"]).lower()
    if validation_status not in VALIDATION_STATUSES:
        allowed = ", ".join(sorted(VALIDATION_STATUSES))
        raise ValueError(f"validation_status must be one of: {allowed}")

    storage_backend = str(manifest["storage_backend"]).lower()
    if storage_backend not in {"local", "s3"}:
        raise ValueError("storage_backend must be one of: local, s3")

    return {
        **manifest,
        "storage_backend": storage_backend,
        "validation_status": validation_status,
    }


def normalize_manifest_storage_fields(manifest: dict[str, Any]) -> dict[str, Any]:
    """Fill route-compatible storage fields when older payloads omit them."""
    normalized = dict(manifest)
    storage_backend = str(normalized.get("storage_backend") or "").lower()
    # Older/local manifests may omit raw_uri or storage_backend. Normalize them
    # so validation, raw loading, and cloud promotion share one field contract.
    if not storage_backend:
        storage_backend = "s3" if not normalized.get("local_raw_path") else "local"
    normalized["storage_backend"] = storage_backend

    if not normalized.get("raw_uri"):
        if storage_backend == "s3":
            normalized["raw_uri"] = normalized.get("s3_raw_uri")
        else:
            normalized["raw_uri"] = normalized.get("local_raw_path")
    return normalized


def write_manifest(
    manifest: ExtractionManifest | dict[str, Any],
    path: Path | str,
) -> Path:
    """Write a manifest JSON file to a local path."""
    payload = manifest_to_json_bytes(manifest)
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(payload)
    return output_path


def manifest_to_json_bytes(manifest: ExtractionManifest | dict[str, Any]) -> bytes:
    """Serialize a manifest as stable, UTF-8 JSON bytes."""
    manifest_dict = (
        manifest.to_dict()
        if isinstance(manifest, ExtractionManifest)
        else validate_manifest(manifest)
    )
    return (json.dumps(manifest_dict, indent=2, sort_keys=True) + "\n").encode("utf-8")


def build_local_manifest_path(
    *,
    data_root: Path,
    source_directory: str,
    ingestion_date: str,
    pipeline_run_id: str,
    filename: str,
) -> Path:
    """Build the local manifest path for a source/run partition."""
    return (
        data_root
        / "manifests"
        / source_directory
        / f"ingestion_date={ingestion_date}"
        / f"pipeline_run_id={pipeline_run_id}"
        / filename
    )


def build_manifest_artifact_location(
    manifest_artifact_store: Any,
    *,
    manifest: ExtractionManifest,
    filename: str,
) -> Any:
    """Build the routed artifact location for a manifest file."""
    return manifest_artifact_store.location(
        prefix="manifests",
        source_system=manifest.source_system,
        dataset_name=manifest.dataset_name,
        resource_name=manifest.resource_name,
        ingestion_date=manifest.ingestion_date,
        pipeline_run_id=manifest.pipeline_run_id,
        filename=filename,
    )


def write_extraction_manifest_outputs(
    *,
    data_root: Path,
    source_directory: str,
    manifest: ExtractionManifest,
    filename: str,
    manifest_artifact_store: Any | None = None,
    manifest_payload: ExtractionManifest | dict[str, Any] | None = None,
) -> ManifestWriteResult:
    """Write local and optional routed manifest outputs for an extraction."""
    manifest_path = build_local_manifest_path(
        data_root=data_root,
        source_directory=source_directory,
        ingestion_date=manifest.ingestion_date,
        pipeline_run_id=manifest.pipeline_run_id,
        filename=filename,
    )
    return write_manifest_outputs(
        manifest=manifest,
        manifest_path=manifest_path,
        manifest_artifact_store=manifest_artifact_store,
        manifest_payload=manifest_payload,
    )


def write_manifest_outputs(
    *,
    manifest: ExtractionManifest,
    manifest_path: Path,
    manifest_artifact_store: Any | None = None,
    manifest_payload: ExtractionManifest | dict[str, Any] | None = None,
) -> ManifestWriteResult:
    """Write a manifest locally and optionally through an artifact store."""
    payload = manifest_payload or manifest
    write_manifest(payload, manifest_path)

    manifest_location = None
    if manifest_artifact_store is not None:
        # The location is based on the canonical manifest metadata, while
        # manifest_payload may include source-specific extra fields in the JSON.
        manifest_location = build_manifest_artifact_location(
            manifest_artifact_store,
            manifest=manifest,
            filename=manifest_path.name,
        )
        manifest_artifact_store.write_bytes(
            manifest_location,
            manifest_to_json_bytes(payload),
        )

    return ManifestWriteResult(
        manifest_path=manifest_path,
        manifest_location=manifest_location,
    )


def _validate_utc_timestamp(value: str) -> None:
    """Require an ISO timestamp with UTC timezone information."""
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.tzinfo is None or timestamp.utcoffset().total_seconds() != 0:
        raise ValueError("extracted_at_utc must be UTC")


def _validate_ingestion_date(value: str) -> None:
    """Require a YYYY-MM-DD ingestion date."""
    datetime.strptime(value, "%Y-%m-%d")


def _validate_non_negative_int(field_name: str, value: Any) -> None:
    """Require a manifest integer field to be non-negative."""
    if not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")


def _is_blank_required_field(manifest: dict[str, Any], field_name: str) -> bool:
    """Return whether a required manifest field is blank for this route."""
    if field_name == "local_raw_path" and manifest.get("storage_backend") == "s3":
        return False
    return manifest[field_name] in ("", None)
