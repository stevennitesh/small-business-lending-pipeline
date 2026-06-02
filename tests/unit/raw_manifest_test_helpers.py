from __future__ import annotations

import json
from pathlib import Path

from pipelines.storage.raw_artifacts import RawArtifactReader
from pipelines.utils.hashing import calculate_sha256, hash_bytes, hash_schema
from pipelines.validation.raw_validation_models import RawManifest
from pipelines.validation.raw_validation_resources import CENSUS_BDS_RESOURCE_NAME


DEFAULT_RAW_JSON_PAYLOAD = '[["YEAR","state"],["2023","01"]]\n'


def write_raw_file(
    tmp_path: Path,
    payload: str = DEFAULT_RAW_JSON_PAYLOAD,
    *,
    filename: str = f"{CENSUS_BDS_RESOURCE_NAME}.json",
) -> Path:
    """Write raw file for tests."""
    raw_file = tmp_path / filename
    raw_file.write_text(payload, encoding="utf-8")
    return raw_file


def write_manifest(
    tmp_path: Path,
    manifest: RawManifest,
    *,
    filename: str = "manifest.json",
) -> Path:
    """Write manifest for tests."""
    manifest_path = tmp_path / filename
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


def manifest_for(raw_file: Path) -> RawManifest:
    """Build manifest for for tests."""
    return {
        "pipeline_run_id": "run-123",
        "source_system": "census",
        "dataset_name": "bds",
        "resource_name": CENSUS_BDS_RESOURCE_NAME,
        "source_url": "https://example.test/source",
        "extracted_at_utc": "2026-05-07T12:00:00Z",
        "ingestion_date": "2026-05-07",
        "local_raw_path": str(raw_file),
        "raw_uri": str(raw_file),
        "s3_raw_uri": "s3://bucket/raw/census/bds/file.json",
        "storage_backend": "local",
        "file_format": "json",
        "row_count": 2,
        "sha256_checksum": calculate_sha256(raw_file),
        "schema_hash": hash_schema(["YEAR", "state"]),
        "validation_status": "passed",
        "column_count": 2,
        "file_size_bytes": raw_file.stat().st_size,
    }


def sba_manifest_for(
    raw_file: Path,
    *,
    source_system: str = "sba",
    dataset_name: str = "7a_504_foia",
    resource_name: str = "sba_7a_fy2020_present",
) -> RawManifest:
    """Build SBA manifest for for tests."""
    manifest = manifest_for(raw_file)
    manifest.update(
        {
            "source_system": source_system,
            "dataset_name": dataset_name,
            "resource_name": resource_name,
        }
    )
    return manifest


def s3_manifest_for(
    raw_payload: bytes,
    *,
    raw_uri: str = "s3://bucket/raw/census/bds/file.json",
) -> RawManifest:
    """Build S3 manifest for for tests."""
    return {
        "pipeline_run_id": "run-123",
        "source_system": "census",
        "dataset_name": "bds",
        "resource_name": CENSUS_BDS_RESOURCE_NAME,
        "source_url": "https://example.test/source",
        "extracted_at_utc": "2026-05-07T12:00:00Z",
        "ingestion_date": "2026-05-07",
        "local_raw_path": None,
        "raw_uri": raw_uri,
        "s3_raw_uri": raw_uri,
        "storage_backend": "s3",
        "file_format": "json",
        "row_count": 2,
        "sha256_checksum": hash_bytes(raw_payload),
        "schema_hash": hash_schema(["YEAR", "state"]),
        "validation_status": "passed",
        "column_count": 2,
        "file_size_bytes": len(raw_payload),
    }


class CountingRawArtifactReader(RawArtifactReader):
    """Raw artifact reader test double that records existence checks."""

    def __init__(self) -> None:
        """Initialize the test double."""
        super().__init__()
        self.exists_calls = 0

    def exists(self, manifest: RawManifest) -> bool:
        """Return whether the fake raw artifact exists."""
        self.exists_calls += 1
        return True
