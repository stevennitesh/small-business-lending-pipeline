from __future__ import annotations

import json

import duckdb
import pytest

from pipelines.load import raw_load_local_sources
from pipelines.load.duckdb_loader import (
    RAW_TABLES,
    RawLoadError,
    load_raw_extracts,
)
from pipelines.validation.validation_result_io import write_validation_results
from tests.unit.raw_load_test_helpers import (
    build_raw_load_fixture_manifests,
    raw_load_validation_result,
    write_raw_load_manifest,
)


def test_load_raw_extracts_creates_tables_and_reconciles_row_counts(tmp_path):
    manifests = build_raw_load_fixture_manifests(tmp_path)
    validation_path = write_validation_results(
        [raw_load_validation_result()],
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
    manifests = build_raw_load_fixture_manifests(tmp_path)
    second_sba_7a = tmp_path / "raw" / "sba_7a_extra.csv"
    second_sba_7a.write_text(
        "GrossApproval,ExtraField,LoanNumber\nnot_available,new-column-value,A-4\n",
        encoding="utf-8",
    )
    manifests["sba_7a"].append(
        write_raw_load_manifest(
            raw_file=second_sba_7a,
            manifest_path=tmp_path / "manifests" / "sba_7a_extra.manifest.json",
            source_system="sba",
            dataset_name="7a_504_foia",
            resource_name="sba_7a_extra",
            row_count=1,
            file_format="csv",
            schema_fields=["GrossApproval", "ExtraField", "LoanNumber"],
        )
    )
    validation_path = write_validation_results(
        [raw_load_validation_result()],
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
              cast(ExtraField as varchar),
              source_resource_name
            from raw.raw_sba_7a_foia
            order by 1
            """
        ).fetchall()

    assert loaded_rows == [
        ("1", "1000", None, "sba_7a_fy2020_present"),
        ("2", "2000", None, "sba_7a_fy2020_present"),
        ("A-4", "not_available", "new-column-value", "sba_7a_extra"),
    ]


def test_load_raw_extracts_does_not_use_pandas_read_csv_for_sba_csvs(
    tmp_path,
    monkeypatch,
):
    manifests = build_raw_load_fixture_manifests(tmp_path)
    validation_path = write_validation_results(
        [raw_load_validation_result()],
        tmp_path / "validation" / "validation_results.json",
    )

    def fail_read_csv(*args, **kwargs):
        raise AssertionError("SBA CSV raw load should use DuckDB native scans")

    monkeypatch.setattr(raw_load_local_sources.pd, "read_csv", fail_read_csv)

    summary = load_raw_extracts(
        duckdb_path=tmp_path / "warehouse.duckdb",
        sba_7a_manifest_paths=manifests["sba_7a"],
        sba_504_manifest_paths=manifests["sba_504"],
        census_bds_manifest_paths=manifests["census"],
        bls_laus_manifest_paths=manifests["bls"],
        validation_result_paths=[validation_path],
    )

    assert summary.table_row_counts["raw.raw_sba_7a_foia"] == 2
    assert summary.table_row_counts["raw.raw_sba_504_foia"] == 1


def test_load_raw_extracts_ignores_hive_partition_folders_for_sba_csvs(tmp_path):
    manifests = build_raw_load_fixture_manifests(tmp_path)
    partitioned_dir = (
        tmp_path
        / "raw"
        / "ingestion_date=2026-05-07"
        / "pipeline_run_id=run-123"
    )
    partitioned_dir.mkdir(parents=True)
    partitioned_sba_7a = partitioned_dir / "sba_7a.csv"
    partitioned_sba_7a.write_text(
        "LoanNumber,GrossApproval\n1,1000\n2,2000\n",
        encoding="utf-8",
    )
    manifests["sba_7a"] = [
        write_raw_load_manifest(
            raw_file=partitioned_sba_7a,
            manifest_path=tmp_path / "manifests" / "partitioned_sba_7a.manifest.json",
            source_system="sba",
            dataset_name="7a_504_foia",
            resource_name="sba_7a_fy2020_present",
            row_count=2,
            file_format="csv",
            schema_fields=["LoanNumber", "GrossApproval"],
        )
    ]
    validation_path = write_validation_results(
        [raw_load_validation_result()],
        tmp_path / "validation" / "validation_results.json",
    )

    load_raw_extracts(
        duckdb_path=tmp_path / "warehouse.duckdb",
        sba_7a_manifest_paths=manifests["sba_7a"],
        sba_504_manifest_paths=manifests["sba_504"],
        census_bds_manifest_paths=manifests["census"],
        bls_laus_manifest_paths=manifests["bls"],
        validation_result_paths=[validation_path],
    )

    with duckdb.connect(str(tmp_path / "warehouse.duckdb")) as connection:
        columns = {
            row[0]
            for row in connection.execute(
                """
                select column_name
                from information_schema.columns
                where table_schema = 'raw'
                  and table_name = 'raw_sba_7a_foia'
                """
            ).fetchall()
        }
        rows = connection.execute(
            """
            select pipeline_run_id, ingestion_date
            from raw.raw_sba_7a_foia
            order by LoanNumber
            """
        ).fetchall()

    assert columns >= {"pipeline_run_id", "ingestion_date"}
    assert rows == [("run-123", "2026-05-07"), ("run-123", "2026-05-07")]


def test_load_raw_extracts_blocks_failed_validation(tmp_path):
    manifests = build_raw_load_fixture_manifests(tmp_path)
    validation_path = write_validation_results(
        [raw_load_validation_result(status="failed")],
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
    manifests = build_raw_load_fixture_manifests(tmp_path)
    validation_path = write_validation_results(
        [raw_load_validation_result()],
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
    manifests = build_raw_load_fixture_manifests(tmp_path)
    validation_path = write_validation_results(
        [raw_load_validation_result()],
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
