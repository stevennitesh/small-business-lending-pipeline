from __future__ import annotations

import json
from pathlib import Path

from pipelines.storage.raw_artifacts import ArtifactLocation
from pipelines.utils.hashing import calculate_sha256, hash_schema
from pipelines.validation.validation_result import ValidationResult


def write_raw_load_manifest(
    *,
    raw_file: Path,
    manifest_path: Path,
    source_system: str,
    dataset_name: str,
    resource_name: str,
    row_count: int,
    file_format: str,
    schema_fields: list[str],
) -> Path:
    """Write a manifest fixture for raw load tests."""
    manifest = {
        "pipeline_run_id": "run-123",
        "source_system": source_system,
        "dataset_name": dataset_name,
        "resource_name": resource_name,
        "source_url": "https://example.test/source",
        "extracted_at_utc": "2026-05-07T12:00:00Z",
        "ingestion_date": "2026-05-07",
        "storage_backend": "local",
        # The fixture includes both local and S3 identities so tests can toggle
        # route behavior without rebuilding source payloads.
        "raw_uri": str(raw_file),
        "local_raw_path": str(raw_file),
        "s3_raw_uri": f"s3://bucket/raw/{source_system}/{dataset_name}/{raw_file.name}",
        "file_format": file_format,
        "row_count": row_count,
        "sha256_checksum": calculate_sha256(raw_file),
        "schema_hash": hash_schema(schema_fields),
        "validation_status": "passed",
        "column_count": len(schema_fields),
        "file_size_bytes": raw_file.stat().st_size,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


def raw_load_validation_result(status: str = "passed") -> ValidationResult:
    """Build a raw validation gate result for raw load tests."""
    return ValidationResult(
        pipeline_run_id="run-123",
        validation_check_id="RAW_001",
        validation_scope="raw",
        source_system="pipeline",
        source_dataset="raw",
        source_resource_name="all",
        check_name="Raw validation gate",
        check_type="validity",
        severity="fail",
        status=status,
        expected_value="raw validation passed",
        observed_value=status,
        message=f"Validation status is {status}.",
        checked_at_utc="2026-05-07T12:00:00Z",
    )


def build_raw_load_fixture_manifests(tmp_path: Path) -> dict[str, list[Path]]:
    """Build fixture raw files and manifests for every raw load source group."""
    raw_dir = tmp_path / "raw"
    manifest_dir = tmp_path / "manifests"
    raw_dir.mkdir()

    sba_7a = raw_dir / "sba_7a.csv"
    sba_7a.write_text("LoanNumber,GrossApproval\n1,1000\n2,2000\n", encoding="utf-8")
    sba_504 = raw_dir / "sba_504.csv"
    sba_504.write_text("LoanNumber,GrossApproval\n3,3000\n", encoding="utf-8")
    census = raw_dir / "bds_state_year.json"
    census.write_text(
        json.dumps([["YEAR", "state", "ESTAB"], ["2023", "01", "98246"]]),
        encoding="utf-8",
    )
    bls = raw_dir / "bls_laus_state_month.json"
    bls.write_text(
        json.dumps(
            {
                "normalized_rows": [
                    {
                        "series_id": "LASST010000000000003",
                        "state_fips": "01",
                        "observed_month": "2023-01-01",
                        "value": 2.6,
                        "footnotes": [],
                    },
                    {
                        "series_id": "LASST020000000000003",
                        "state_fips": "02",
                        "observed_month": "2023-01-01",
                        "value": 3.8,
                        "footnotes": [],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    return {
        "sba_7a": [
            write_raw_load_manifest(
                raw_file=sba_7a,
                manifest_path=manifest_dir / "sba_7a.manifest.json",
                source_system="sba",
                dataset_name="7a_504_foia",
                resource_name="sba_7a_fy2020_present",
                row_count=2,
                file_format="csv",
                schema_fields=["LoanNumber", "GrossApproval"],
            )
        ],
        "sba_504": [
            write_raw_load_manifest(
                raw_file=sba_504,
                manifest_path=manifest_dir / "sba_504.manifest.json",
                source_system="sba",
                dataset_name="7a_504_foia",
                resource_name="sba_504_fy2010_present",
                row_count=1,
                file_format="csv",
                schema_fields=["LoanNumber", "GrossApproval"],
            )
        ],
        "census": [
            write_raw_load_manifest(
                raw_file=census,
                manifest_path=manifest_dir / "census.manifest.json",
                source_system="census",
                dataset_name="bds",
                resource_name="bds_state_year",
                row_count=1,
                file_format="json",
                schema_fields=["YEAR", "state", "ESTAB"],
            )
        ],
        "bls": [
            write_raw_load_manifest(
                raw_file=bls,
                manifest_path=manifest_dir / "bls.manifest.json",
                source_system="bls",
                dataset_name="laus",
                resource_name="laus_state_month",
                row_count=2,
                file_format="json",
                schema_fields=["series_id", "state_fips", "observed_month", "value"],
            )
        ],
    }


def make_manifests_s3_backed(manifests: dict[str, list[Path]]) -> None:
    """Rewrite manifest fixtures to behave like cloud-backed manifests."""
    for manifest_paths in manifests.values():
        for manifest_path in manifest_paths:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["storage_backend"] = "s3"
            manifest["raw_uri"] = manifest["s3_raw_uri"]
            manifest["local_raw_path"] = None
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


def manifest_artifact_locations(
    manifests: dict[str, list[Path]],
) -> tuple[dict[str, list[ArtifactLocation]], dict[tuple[str, str], bytes]]:
    """Build artifact locations and fake S3 objects for manifest fixtures."""
    objects: dict[tuple[str, str], bytes] = {}
    locations: dict[str, list[ArtifactLocation]] = {}
    for source_group, manifest_paths in manifests.items():
        locations[source_group] = []
        for manifest_path in manifest_paths:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            key = (
                f"manifests/{manifest['source_system']}/{manifest['dataset_name']}/"
                f"{manifest['resource_name']}/"
                f"ingestion_date={manifest['ingestion_date']}/"
                f"pipeline_run_id={manifest['pipeline_run_id']}/"
                f"{manifest_path.name}"
            )
            objects[("bucket", key)] = manifest_path.read_bytes()
            locations[source_group].append(
                ArtifactLocation(
                    storage_backend="s3",
                    artifact_uri=f"s3://bucket/{key}",
                    artifact_key=key,
                    s3_uri=f"s3://bucket/{key}",
                )
            )
    return locations, objects
