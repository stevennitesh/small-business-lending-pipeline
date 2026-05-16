from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from pipelines.load.snowflake_loader import (
    REQUIRED_SCHEMAS,
    SNOWFLAKE_RAW_TABLES,
    SnowflakeRawLoadError,
    load_raw_extracts_to_snowflake_from_s3,
    load_raw_extracts_to_snowflake,
)
from pipelines.utils.hashing import calculate_sha256, hash_schema
from pipelines.validation.validation_result import (
    ValidationResult,
    write_validation_results,
)


def test_snowflake_loader_creates_schemas_tables_and_reconciles_counts(tmp_path):
    manifests = _build_fixture_manifests(tmp_path)
    validation_path = write_validation_results(
        [_validation_result()],
        tmp_path / "validation" / "validation_results.json",
    )
    connection = FakeSnowflakeConnection()
    writer = FakeSnowflakeWriter()

    summary = load_raw_extracts_to_snowflake(
        connection=connection,
        database="SMALL_BUSINESS_LENDING",
        raw_schema="RAW",
        audit_schema="AUDIT",
        sba_7a_manifest_paths=manifests["sba_7a"],
        sba_504_manifest_paths=manifests["sba_504"],
        census_bds_manifest_paths=manifests["census"],
        bls_laus_manifest_paths=manifests["bls"],
        validation_result_paths=[validation_path],
        write_pandas_func=writer,
    )

    for schema_name in REQUIRED_SCHEMAS:
        assert f"create schema if not exists {schema_name}" in connection.sql_statements

    assert set(SNOWFLAKE_RAW_TABLES.values()) <= set(writer.written_frames)
    assert summary.table_row_counts["RAW.RAW_SBA_7A_FOIA"] == 2
    assert summary.table_row_counts["RAW.RAW_SBA_504_FOIA"] == 1
    assert summary.table_row_counts["RAW.RAW_CENSUS_BDS_STATE_YEAR"] == 1
    assert summary.table_row_counts["RAW.RAW_BLS_LAUS_STATE_MONTH"] == 2
    assert summary.table_row_counts["RAW.RAW_INGESTION_MANIFEST"] == 4
    assert summary.table_row_counts["RAW.RAW_VALIDATION_RESULT"] == 1
    assert summary.table_row_counts["RAW.RAW_PIPELINE_RUN_SUMMARY"] == 1
    assert summary.pipeline_run_ids == ("run-123",)

    loaded_sba = writer.written_frames["RAW_SBA_7A_FOIA"]
    assert {
        "PIPELINE_RUN_ID",
        "SOURCE_SYSTEM",
        "SOURCE_DATASET",
        "SOURCE_RESOURCE_NAME",
        "INGESTION_DATE",
        "STORAGE_BACKEND",
        "RAW_URI",
        "RAW_FILE_PATH",
        "S3_RAW_URI",
        "SHA256_CHECKSUM",
    } <= set(loaded_sba.columns)
    sba_manifest = json.loads(manifests["sba_7a"][0].read_text(encoding="utf-8"))
    assert loaded_sba["PIPELINE_RUN_ID"].tolist() == ["run-123", "run-123"]
    assert loaded_sba["STORAGE_BACKEND"].tolist() == ["local", "local"]
    assert loaded_sba["RAW_URI"].tolist() == [
        sba_manifest["local_raw_path"],
        sba_manifest["local_raw_path"],
    ]
    assert loaded_sba["S3_RAW_URI"].tolist() == [
        "s3://bucket/raw/sba/7a_504_foia/sba_7a.csv",
        "s3://bucket/raw/sba/7a_504_foia/sba_7a.csv",
    ]
    validation_frame = writer.written_frames["RAW_VALIDATION_RESULT"]
    assert validation_frame["EXPECTED_VALUE"].tolist() == ["1"]
    assert validation_frame["OBSERVED_VALUE"].tolist() == ['{"status": "passed"}']
    loaded_bls = writer.written_frames["RAW_BLS_LAUS_STATE_MONTH"]
    assert loaded_bls["FOOTNOTES"].tolist() == ["[]", "[]"]


def test_snowflake_s3_loader_uses_stage_copy_and_writes_metadata(tmp_path):
    manifests = _build_fixture_manifests(tmp_path)
    _make_manifests_s3_backed(manifests)
    validation_path = write_validation_results(
        [_validation_result()],
        tmp_path / "validation" / "validation_results.json",
    )
    connection = FakeSnowflakeConnection(
        table_counts={
            "RAW.RAW_SBA_7A_FOIA": 2,
            "RAW.RAW_SBA_504_FOIA": 1,
            "RAW.RAW_CENSUS_BDS_STATE_YEAR": 1,
            "RAW.RAW_BLS_LAUS_STATE_MONTH": 2,
        }
    )
    writer = FakeSnowflakeWriter()

    summary = load_raw_extracts_to_snowflake_from_s3(
        connection=connection,
        database="SMALL_BUSINESS_LENDING",
        raw_schema="RAW",
        audit_schema="AUDIT",
        sba_7a_manifest_paths=manifests["sba_7a"],
        sba_504_manifest_paths=manifests["sba_504"],
        census_bds_manifest_paths=manifests["census"],
        bls_laus_manifest_paths=manifests["bls"],
        validation_result_paths=[validation_path],
        write_pandas_func=writer,
        storage_integration="SBL_S3_INT",
    )

    sql = " ".join(connection.sql_statements)
    assert "create stage if not exists RAW.RAW_S3_STAGE" in sql
    assert "storage_integration = SBL_S3_INT" in sql
    assert (
        "create or replace table RAW.RAW_SBA_7A_FOIA using template"
        in sql
    )
    assert (
        "alter table RAW.RAW_SBA_7A_FOIA add column if not exists RAW_URI varchar"
        in sql
    )
    assert "update RAW.RAW_SBA_7A_FOIA set" in sql
    assert "STORAGE_BACKEND = 's3'" in sql
    assert "RAW_URI = 's3://bucket/raw/sba/7a_504_foia/sba_7a.csv'" in sql
    assert "create or replace table RAW.RAW_CENSUS_BDS_STATE_YEAR" in sql
    assert "insert into RAW.RAW_CENSUS_BDS_STATE_YEAR" in sql
    assert "lateral flatten(input => PAYLOAD) as row" in sql
    assert "create or replace table RAW.RAW_BLS_LAUS_STATE_MONTH" in sql
    assert "insert into RAW.RAW_BLS_LAUS_STATE_MONTH" in sql
    assert "lateral flatten(input => PAYLOAD:normalized_rows) as row" in sql
    assert any(
        statement.startswith("copy into RAW.RAW_SBA_7A_FOIA")
        for statement in connection.sql_statements
    )
    assert summary.table_row_counts["RAW.RAW_SBA_7A_FOIA"] == 2
    assert summary.table_row_counts["RAW.RAW_INGESTION_MANIFEST"] == 4
    summary_frame = writer.written_frames["RAW_PIPELINE_RUN_SUMMARY"]
    assert summary_frame["LOAD_PATTERN"].tolist() == ["s3_stage_copy"]


def test_snowflake_loader_blocks_failed_validation(tmp_path):
    manifests = _build_fixture_manifests(tmp_path)
    validation_path = write_validation_results(
        [_validation_result(status="failed")],
        tmp_path / "validation" / "validation_results.json",
    )

    with pytest.raises(SnowflakeRawLoadError, match="Critical raw validation failures"):
        load_raw_extracts_to_snowflake(
            connection=FakeSnowflakeConnection(),
            database="SMALL_BUSINESS_LENDING",
            raw_schema="RAW",
            audit_schema="AUDIT",
            sba_7a_manifest_paths=manifests["sba_7a"],
            sba_504_manifest_paths=manifests["sba_504"],
            census_bds_manifest_paths=manifests["census"],
            bls_laus_manifest_paths=manifests["bls"],
            validation_result_paths=[validation_path],
            write_pandas_func=FakeSnowflakeWriter(),
        )


def test_snowflake_loader_rejects_empty_required_manifest_group(tmp_path):
    manifests = _build_fixture_manifests(tmp_path)
    validation_path = write_validation_results(
        [_validation_result()],
        tmp_path / "validation" / "validation_results.json",
    )

    with pytest.raises(SnowflakeRawLoadError, match="Required manifest group is empty"):
        load_raw_extracts_to_snowflake(
            connection=FakeSnowflakeConnection(),
            database="SMALL_BUSINESS_LENDING",
            raw_schema="RAW",
            audit_schema="AUDIT",
            sba_7a_manifest_paths=manifests["sba_7a"],
            sba_504_manifest_paths=manifests["sba_504"],
            census_bds_manifest_paths=[],
            bls_laus_manifest_paths=manifests["bls"],
            validation_result_paths=[validation_path],
            write_pandas_func=FakeSnowflakeWriter(),
        )


def test_snowflake_loader_rejects_row_count_mismatch(tmp_path):
    manifests = _build_fixture_manifests(tmp_path)
    validation_path = write_validation_results(
        [_validation_result()],
        tmp_path / "validation" / "validation_results.json",
    )
    manifest_path = manifests["sba_7a"][0]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["row_count"] = 999
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(SnowflakeRawLoadError, match="Row count mismatch"):
        load_raw_extracts_to_snowflake(
            connection=FakeSnowflakeConnection(),
            database="SMALL_BUSINESS_LENDING",
            raw_schema="RAW",
            audit_schema="AUDIT",
            sba_7a_manifest_paths=manifests["sba_7a"],
            sba_504_manifest_paths=manifests["sba_504"],
            census_bds_manifest_paths=manifests["census"],
            bls_laus_manifest_paths=manifests["bls"],
            validation_result_paths=[validation_path],
            write_pandas_func=FakeSnowflakeWriter(),
        )


class FakeSnowflakeConnection:
    def __init__(self, table_counts: dict[str, int] | None = None) -> None:
        self.sql_statements: list[str] = []
        self.table_counts = table_counts or {}

    def cursor(self):
        return FakeSnowflakeCursor(self)


class FakeSnowflakeCursor:
    def __init__(self, connection: FakeSnowflakeConnection) -> None:
        self.connection = connection
        self.result: tuple[int] | None = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, sql: str):
        normalized_sql = " ".join(sql.split())
        self.connection.sql_statements.append(normalized_sql)
        if normalized_sql.lower().startswith("select count(*) from "):
            table_name = normalized_sql.rsplit(" ", 1)[-1]
            self.result = (self.connection.table_counts[table_name],)
        return self

    def fetchone(self):
        if self.result is None:
            raise AssertionError("No fake result available")
        return self.result


class FakeSnowflakeWriter:
    def __init__(self) -> None:
        self.written_frames: dict[str, pd.DataFrame] = {}

    def __call__(
        self,
        connection,
        frame: pd.DataFrame,
        table_name: str,
        **kwargs,
    ) -> tuple[bool, int, int, list[tuple[str, str]]]:
        self.written_frames[table_name] = frame.copy()
        return True, 1, len(frame), []


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
        expected_value=1,
        observed_value={"status": status},
        message=f"Validation status is {status}.",
        checked_at_utc="2026-05-07T12:00:00Z",
    )


def _make_manifests_s3_backed(manifests: dict[str, list[Path]]) -> None:
    for manifest_paths in manifests.values():
        for manifest_path in manifest_paths:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["storage_backend"] = "s3"
            manifest["raw_uri"] = manifest["s3_raw_uri"]
            manifest["local_raw_path"] = None
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


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
