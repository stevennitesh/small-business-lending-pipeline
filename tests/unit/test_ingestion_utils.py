from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from pipelines.utils.dates import ingestion_date_from_timestamp, utc_now_iso
from pipelines.utils.hashing import calculate_sha256, hash_row, hash_schema
from pipelines.utils.manifest import (
    REQUIRED_MANIFEST_FIELDS,
    ExtractionManifest,
    validate_manifest,
)
from pipelines.utils.paths import (
    build_local_raw_path,
    build_raw_s3_key,
    build_s3_uri,
)


def test_sha256_checksum_is_deterministic(tmp_path):
    file_path = tmp_path / "sample.csv"
    file_path.write_text("a,b\n1,2\n", encoding="utf-8")

    first = calculate_sha256(file_path)
    second = calculate_sha256(file_path)

    assert first == second
    assert len(first) == 64


def test_row_and_schema_hashes_are_deterministic():
    assert hash_row({"state": "TX", "loans": 10}) == hash_row(
        {"loans": 10, "state": "TX"}
    )
    assert hash_schema(
        [
            {"name": "state", "type": "string"},
            {"name": "loans", "type": "integer"},
        ]
    ) == hash_schema(
        [
            {"type": "string", "name": "state"},
            {"type": "integer", "name": "loans"},
        ]
    )


def test_raw_paths_follow_partitioning_convention():
    key = build_raw_s3_key(
        source_system="sba",
        dataset_name="7a_foia",
        resource_name="source_period=fy2020_present",
        ingestion_date="2026-05-06",
        pipeline_run_id="run-123",
        filename="foia_7a.csv",
    )

    assert key == (
        "raw/sba/7a_foia/source_period=fy2020_present/"
        "ingestion_date=2026-05-06/pipeline_run_id=run-123/foia_7a.csv"
    )
    assert build_s3_uri("example-bucket", key) == f"s3://example-bucket/{key}"
    assert build_local_raw_path(
        data_root=Path("data"),
        source_system="sba",
        dataset_name="7a_foia",
        resource_name="source_period=fy2020_present",
        ingestion_date="2026-05-06",
        pipeline_run_id="run-123",
        filename="foia_7a.csv",
    ) == Path(
        "data/raw/sba/7a_foia/source_period=fy2020_present/"
        "ingestion_date=2026-05-06/pipeline_run_id=run-123/foia_7a.csv"
    )


def test_timestamps_are_utc():
    timestamp = utc_now_iso()

    assert timestamp.endswith("Z")
    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    assert parsed.tzinfo == timezone.utc
    assert ingestion_date_from_timestamp(parsed) == parsed.date().isoformat()


def test_manifest_contains_required_fields_and_validates():
    manifest = ExtractionManifest(
        pipeline_run_id="run-123",
        source_system="sba",
        dataset_name="7a_foia",
        resource_name="source_period=fy2020_present",
        source_url="https://example.com/foia_7a.csv",
        extracted_at_utc="2026-05-06T12:00:00Z",
        ingestion_date="2026-05-06",
        local_raw_path="data/raw/sba/7a_foia/file.csv",
        s3_raw_uri="s3://bucket/raw/sba/7a_foia/file.csv",
        file_format="csv",
        row_count=2,
        sha256_checksum="0" * 64,
        schema_hash="1" * 64,
        validation_status="passed",
    )

    manifest_dict = manifest.to_dict()

    assert REQUIRED_MANIFEST_FIELDS <= set(manifest_dict)
    assert manifest_dict["storage_backend"] == "local"
    assert manifest_dict["raw_uri"] == manifest_dict["local_raw_path"]
    assert validate_manifest(manifest_dict) == manifest_dict


def test_manifest_validation_accepts_s3_backed_raw_uri():
    manifest = {
        "pipeline_run_id": "run-123",
        "source_system": "census",
        "dataset_name": "bds",
        "resource_name": "bds_state_year",
        "source_url": "https://example.com/bds",
        "extracted_at_utc": "2026-05-06T12:00:00Z",
        "ingestion_date": "2026-05-06",
        "storage_backend": "s3",
        "raw_uri": "s3://bucket/raw/census/bds/file.json",
        "local_raw_path": None,
        "s3_raw_uri": "s3://bucket/raw/census/bds/file.json",
        "file_format": "json",
        "row_count": 2,
        "sha256_checksum": "0" * 64,
        "schema_hash": "1" * 64,
        "validation_status": "passed",
    }

    assert validate_manifest(manifest) == manifest


def test_manifest_validation_rejects_missing_required_fields():
    with pytest.raises(ValueError, match="Missing required manifest fields"):
        validate_manifest({"pipeline_run_id": "run-123"})


def test_manifest_validation_rejects_non_utc_timestamp():
    manifest = {
        field_name: "value"
        for field_name in REQUIRED_MANIFEST_FIELDS
    }
    manifest.update(
        {
            "extracted_at_utc": "2026-05-06T12:00:00",
            "ingestion_date": "2026-05-06",
            "row_count": 0,
            "validation_status": "passed",
        }
    )

    with pytest.raises(ValueError, match="extracted_at_utc must be UTC"):
        validate_manifest(manifest)
