from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from pipelines.load.duckdb_loader import (
    RAW_TABLES,
    RawLoadError,
    load_raw_extracts,
)
from pipelines.utils.hashing import calculate_sha256, hash_schema
from pipelines.validation.validation_result import (
    ValidationResult,
    write_validation_results,
)


def _write_manifest(
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
    manifest = {
        "pipeline_run_id": "run-123",
        "source_system": source_system,
        "dataset_name": dataset_name,
        "resource_name": resource_name,
        "source_url": "https://example.test/source",
        "extracted_at_utc": "2026-05-07T12:00:00Z",
        "ingestion_date": "2026-05-07",
        "storage_backend": "local",
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


def _validation_result(status: str = "passed") -> ValidationResult:
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


def _build_fixture_manifests(tmp_path: Path) -> dict[str, list[Path]]:
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
                    },
                    {
                        "series_id": "LASST020000000000003",
                        "state_fips": "02",
                        "observed_month": "2023-01-01",
                        "value": 3.8,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    return {
        "sba_7a": [
            _write_manifest(
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
            _write_manifest(
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
            _write_manifest(
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
            _write_manifest(
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


def test_load_raw_extracts_creates_tables_and_reconciles_row_counts(tmp_path):
    manifests = _build_fixture_manifests(tmp_path)
    validation_path = write_validation_results(
        [_validation_result()],
        tmp_path / "validation" / "validation_results.json",
    )
    duckdb_path = tmp_path / "warehouse.duckdb"

    summary = load_raw_extracts(
        duckdb_path=duckdb_path,
        sba_7a_manifest_paths=manifests["sba_7a"],
        sba_504_manifest_paths=manifests["sba_504"],
        census_bds_manifest_paths=manifests["census"],
        bls_laus_manifest_paths=manifests["bls"],
        validation_result_paths=[validation_path],
    )

    assert summary.table_row_counts["raw.raw_sba_7a_foia"] == 2
    assert summary.table_row_counts["raw.raw_sba_504_foia"] == 1
    assert summary.table_row_counts["raw.raw_census_bds_state_year"] == 1
    assert summary.table_row_counts["raw.raw_bls_laus_state_month"] == 2
    assert summary.table_row_counts["raw.raw_ingestion_manifest"] == 4
    assert summary.table_row_counts["raw.raw_validation_result"] == 1

    with duckdb.connect(str(duckdb_path)) as connection:
        existing_tables = {
            row[0]
            for row in connection.execute(
                "select table_name from information_schema.tables where table_schema = 'raw'"
            ).fetchall()
        }
        assert set(RAW_TABLES) <= existing_tables
        columns = {
            row[1]
            for row in connection.execute(
                "select table_name, column_name from information_schema.columns "
                "where table_schema = 'raw' and table_name = 'raw_sba_7a_foia'"
            ).fetchall()
        }
        loaded_s3_uri = connection.execute(
            "select distinct s3_raw_uri from raw.raw_sba_7a_foia"
        ).fetchall()
        loaded_raw_uri = connection.execute(
            "select distinct storage_backend, raw_uri from raw.raw_sba_7a_foia"
        ).fetchall()

    assert {
        "pipeline_run_id",
        "source_system",
        "source_dataset",
        "source_resource_name",
        "ingestion_date",
        "storage_backend",
        "raw_uri",
        "raw_file_path",
        "s3_raw_uri",
        "sha256_checksum",
    } <= columns
    assert loaded_s3_uri == [
        ("s3://bucket/raw/sba/7a_504_foia/sba_7a.csv",)
    ]
    expected_manifest = json.loads(manifests["sba_7a"][0].read_text(encoding="utf-8"))
    assert loaded_raw_uri == [("local", expected_manifest["raw_uri"])]


def test_load_raw_extracts_preserves_multiple_sba_manifests_and_raw_values(tmp_path):
    manifests = _build_fixture_manifests(tmp_path)
    second_sba_7a = tmp_path / "raw" / "sba_7a_extra.csv"
    second_sba_7a.write_text(
        "LoanNumber,GrossApproval\nA-4,not_available\n",
        encoding="utf-8",
    )
    manifests["sba_7a"].append(
        _write_manifest(
            raw_file=second_sba_7a,
            manifest_path=tmp_path / "manifests" / "sba_7a_extra.manifest.json",
            source_system="sba",
            dataset_name="7a_504_foia",
            resource_name="sba_7a_extra",
            row_count=1,
            file_format="csv",
            schema_fields=["LoanNumber", "GrossApproval"],
        )
    )
    validation_path = write_validation_results(
        [_validation_result()],
        tmp_path / "validation" / "validation_results.json",
    )

    summary = load_raw_extracts(
        duckdb_path=tmp_path / "warehouse.duckdb",
        sba_7a_manifest_paths=manifests["sba_7a"],
        sba_504_manifest_paths=manifests["sba_504"],
        census_bds_manifest_paths=manifests["census"],
        bls_laus_manifest_paths=manifests["bls"],
        validation_result_paths=[validation_path],
    )

    assert summary.table_row_counts["raw.raw_sba_7a_foia"] == 3

    with duckdb.connect(str(tmp_path / "warehouse.duckdb")) as connection:
        loaded_rows = connection.execute(
            """
            select
              cast(LoanNumber as varchar),
              cast(GrossApproval as varchar),
              source_resource_name
            from raw.raw_sba_7a_foia
            order by 1
            """
        ).fetchall()

    assert loaded_rows == [
        ("1", "1000", "sba_7a_fy2020_present"),
        ("2", "2000", "sba_7a_fy2020_present"),
        ("A-4", "not_available", "sba_7a_extra"),
    ]


def test_load_raw_extracts_blocks_failed_validation(tmp_path):
    manifests = _build_fixture_manifests(tmp_path)
    validation_path = write_validation_results(
        [_validation_result(status="failed")],
        tmp_path / "validation" / "validation_results.json",
    )

    with pytest.raises(RawLoadError, match="Critical raw validation failures"):
        load_raw_extracts(
            duckdb_path=tmp_path / "warehouse.duckdb",
            sba_7a_manifest_paths=manifests["sba_7a"],
            sba_504_manifest_paths=manifests["sba_504"],
            census_bds_manifest_paths=manifests["census"],
            bls_laus_manifest_paths=manifests["bls"],
            validation_result_paths=[validation_path],
        )


def test_load_raw_extracts_rejects_empty_required_manifest_group(tmp_path):
    manifests = _build_fixture_manifests(tmp_path)
    validation_path = write_validation_results(
        [_validation_result()],
        tmp_path / "validation" / "validation_results.json",
    )

    with pytest.raises(RawLoadError, match="Required manifest group is empty"):
        load_raw_extracts(
            duckdb_path=tmp_path / "warehouse.duckdb",
            sba_7a_manifest_paths=manifests["sba_7a"],
            sba_504_manifest_paths=manifests["sba_504"],
            census_bds_manifest_paths=[],
            bls_laus_manifest_paths=manifests["bls"],
            validation_result_paths=[validation_path],
        )


def test_load_raw_extracts_rejects_manifest_row_count_mismatch(tmp_path):
    manifests = _build_fixture_manifests(tmp_path)
    validation_path = write_validation_results(
        [_validation_result()],
        tmp_path / "validation" / "validation_results.json",
    )
    manifest_path = manifests["sba_7a"][0]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["row_count"] = 999
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(RawLoadError, match="Row count mismatch"):
        load_raw_extracts(
            duckdb_path=tmp_path / "warehouse.duckdb",
            sba_7a_manifest_paths=manifests["sba_7a"],
            sba_504_manifest_paths=manifests["sba_504"],
            census_bds_manifest_paths=manifests["census"],
            bls_laus_manifest_paths=manifests["bls"],
            validation_result_paths=[validation_path],
        )
