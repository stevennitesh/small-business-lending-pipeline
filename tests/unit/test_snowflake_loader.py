from __future__ import annotations

import pytest

from pipelines.load.snowflake_loader import (
    REQUIRED_SCHEMAS,
    SNOWFLAKE_RAW_TABLES,
    SnowflakeConfig,
    SnowflakeRawLoadError,
    load_raw_extracts_to_snowflake_from_s3,
)
from pipelines.load.snowflake_stage_load import create_s3_stage_load_objects
from pipelines.load.snowflake_stage_sources import snowflake_csv_columns
from pipelines.storage.raw_artifacts import ArtifactLocation
from pipelines.validation.validation_result_io import write_validation_results
from tests.unit.raw_load_test_helpers import (
    build_raw_load_fixture_manifests,
    make_manifests_s3_backed,
    manifest_artifact_locations,
    raw_load_validation_result,
    write_raw_load_manifest,
)
from tests.unit.snowflake_test_helpers import (
    FakeS3Client,
    FakeSnowflakeConnection,
    FakeSnowflakeWriter,
)


def test_snowflake_config_supports_isolated_raw_schema(monkeypatch):
    """Validate that snowflake config supports isolated raw schema."""
    monkeypatch.setenv("SNOWFLAKE_ACCOUNT", "acct")
    monkeypatch.setenv("SNOWFLAKE_USER", "user")
    monkeypatch.setenv("SNOWFLAKE_PASSWORD", "password")
    monkeypatch.setenv("SNOWFLAKE_ROLE", "role")
    monkeypatch.setenv("SNOWFLAKE_WAREHOUSE", "warehouse")
    monkeypatch.setenv("SNOWFLAKE_DATABASE", "database")
    monkeypatch.setenv("SNOWFLAKE_SCHEMA", "RAW")
    monkeypatch.setenv("RAW_SCHEMA", "SMOKE_RAW")
    monkeypatch.setenv("SNOWFLAKE_STORAGE_INTEGRATION", "")

    config = SnowflakeConfig.from_env()

    assert config.raw_schema == "SMOKE_RAW"
    assert config.storage_integration is None


def test_snowflake_config_ignores_warehouse_default_schema_for_raw_schema(monkeypatch):
    """Validate that snowflake config ignores warehouse default schema for raw schema."""
    monkeypatch.setenv("SNOWFLAKE_ACCOUNT", "acct")
    monkeypatch.setenv("SNOWFLAKE_USER", "user")
    monkeypatch.setenv("SNOWFLAKE_PASSWORD", "password")
    monkeypatch.setenv("SNOWFLAKE_ROLE", "role")
    monkeypatch.setenv("SNOWFLAKE_WAREHOUSE", "warehouse")
    monkeypatch.setenv("SNOWFLAKE_DATABASE", "database")
    monkeypatch.setenv("SNOWFLAKE_SCHEMA", "RAW")
    monkeypatch.setenv("RAW_SCHEMA", "ROUTE_RAW")

    config = SnowflakeConfig.from_env()

    assert config.raw_schema == "ROUTE_RAW"


def test_snowflake_s3_loader_uses_stage_copy_and_writes_metadata(tmp_path):
    """Validate that snowflake S3 loader uses stage copy and writes metadata."""
    manifests = build_raw_load_fixture_manifests(tmp_path)
    sba_7a_part2 = tmp_path / "raw" / "sba_7a_part2.csv"
    sba_7a_part2.write_text("LoanNumber,GrossApproval\n4,4000\n", encoding="utf-8")
    manifests["sba_7a"].append(
        write_raw_load_manifest(
            raw_file=sba_7a_part2,
            manifest_path=tmp_path / "manifests" / "sba_7a_part2.manifest.json",
            source_system="sba",
            dataset_name="7a_504_foia",
            resource_name="sba_7a_fy2000_fy2009",
            row_count=1,
            file_format="csv",
            schema_fields=["LoanNumber", "GrossApproval"],
        )
    )
    make_manifests_s3_backed(manifests)
    validation_path = write_validation_results(
        [raw_load_validation_result()],
        tmp_path / "validation" / "validation_results.json",
    )
    connection = FakeSnowflakeConnection(
        table_counts={
            "RAW.RAW_SBA_7A_FOIA": 3,
            "RAW.RAW_SBA_504_FOIA": 1,
            "RAW.RAW_CENSUS_BDS_STATE_YEAR": 1,
            "RAW.RAW_BLS_LAUS_STATE_MONTH": 2,
        }
    )
    writer = FakeSnowflakeWriter()
    s3_headers = {
        "raw/sba/7a_504_foia/sba_7a.csv": "LoanNumber,GrossApproval\n",
        "raw/sba/7a_504_foia/sba_7a_part2.csv": "LoanNumber,GrossApproval\n",
        "raw/sba/7a_504_foia/sba_504.csv": "LoanNumber,GrossApproval\n",
    }

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
        s3_client=FakeS3Client(s3_headers),
    )

    sql = " ".join(connection.sql_statements)
    for schema_name in REQUIRED_SCHEMAS:
        assert f"create schema if not exists {schema_name}" in connection.sql_statements
    assert 'create or replace file format "RAW"."RAW_CSV_LOAD_FORMAT"' in sql
    assert 'create or replace file format "RAW"."RAW_JSON_FORMAT"' in sql
    assert 'create or replace stage "RAW"."RAW_S3_STAGE"' in sql
    assert 'storage_integration = "SBL_S3_INT"' in sql
    assert "escape_unenclosed_field = none" in sql
    assert "error_on_column_count_mismatch = false" in sql
    assert 'create or replace table "RAW"."RAW_SBA_7A_FOIA" (' in sql
    assert '"LOANNUMBER" varchar' in sql
    assert '"GROSSAPPROVAL" varchar' in sql
    assert "using template" not in sql
    assert '"RAW_URI" varchar' in sql
    assert 'update "RAW"."RAW_SBA_7A_FOIA" set' in sql
    assert "\"STORAGE_BACKEND\" = 's3'" in sql
    assert "lateral flatten(input => PAYLOAD)" in sql
    assert "array_position(to_variant('YEAR'), headers)" in sql
    assert "array_position(to_variant('state'), headers)" in sql
    assert "lateral flatten(input => PAYLOAD:normalized_rows)" in sql
    assert "row.value" not in sql
    assert "\"RAW_URI\" = 's3://bucket/raw/sba/7a_504_foia/sba_7a.csv'" in sql
    assert "\"RAW_URI\" = 's3://bucket/raw/sba/7a_504_foia/sba_7a_part2.csv'" in sql
    first_copy = sql.index('\'@"RAW"."RAW_S3_STAGE"/raw/sba/7a_504_foia/sba_7a.csv\'')
    first_update = sql.index("\"SOURCE_RESOURCE_NAME\" = 'sba_7a_fy2020_present'")
    second_copy = sql.index(
        '\'@"RAW"."RAW_S3_STAGE"/raw/sba/7a_504_foia/sba_7a_part2.csv\''
    )
    second_update = sql.index("\"SOURCE_RESOURCE_NAME\" = 'sba_7a_fy2000_fy2009'")
    assert first_copy < first_update < second_copy < second_update
    assert 'create or replace table "RAW"."RAW_CENSUS_BDS_STATE_YEAR"' in sql
    assert 'insert into "RAW"."RAW_CENSUS_BDS_STATE_YEAR"' in sql
    assert 'create or replace table "RAW"."RAW_BLS_LAUS_STATE_MONTH"' in sql
    assert 'insert into "RAW"."RAW_BLS_LAUS_STATE_MONTH"' in sql
    assert any(
        statement.startswith('copy into "RAW"."RAW_SBA_7A_FOIA"')
        for statement in connection.sql_statements
    )
    assert summary.table_row_counts["RAW.RAW_SBA_7A_FOIA"] == 3
    assert summary.table_row_counts["RAW.RAW_SBA_504_FOIA"] == 1
    assert summary.table_row_counts["RAW.RAW_CENSUS_BDS_STATE_YEAR"] == 1
    assert summary.table_row_counts["RAW.RAW_BLS_LAUS_STATE_MONTH"] == 2
    assert summary.table_row_counts["RAW.RAW_INGESTION_MANIFEST"] == 5
    assert summary.table_row_counts["RAW.RAW_VALIDATION_RESULT"] == 1
    assert summary.table_row_counts["RAW.RAW_PIPELINE_RUN_SUMMARY"] == 1
    assert summary.pipeline_run_ids == ("run-123",)
    assert set(SNOWFLAKE_RAW_TABLES.values()) - {
        "RAW_SBA_7A_FOIA",
        "RAW_SBA_504_FOIA",
        "RAW_CENSUS_BDS_STATE_YEAR",
        "RAW_BLS_LAUS_STATE_MONTH",
    } <= set(writer.written_frames)
    summary_frame = writer.written_frames["RAW_PIPELINE_RUN_SUMMARY"]
    assert summary_frame["LOAD_PATTERN"].tolist() == ["s3_stage_copy"]


def test_snowflake_s3_loader_accepts_cloud_artifact_references(tmp_path):
    """Validate that snowflake S3 loader accepts cloud artifact references."""
    manifests = build_raw_load_fixture_manifests(tmp_path)
    make_manifests_s3_backed(manifests)
    validation_path = write_validation_results(
        [raw_load_validation_result()],
        tmp_path / "validation" / "validation_results.json",
    )
    manifest_locations, s3_objects = manifest_artifact_locations(manifests)
    validation_location = ArtifactLocation(
        storage_backend="s3",
        artifact_uri=(
            "s3://bucket/validation/pipeline/raw_validation/validation_results/"
            "ingestion_date=2026-05-07/pipeline_run_id=run-123/"
            "validation_results.json"
        ),
        artifact_key=(
            "validation/pipeline/raw_validation/validation_results/"
            "ingestion_date=2026-05-07/pipeline_run_id=run-123/"
            "validation_results.json"
        ),
        s3_uri=(
            "s3://bucket/validation/pipeline/raw_validation/validation_results/"
            "ingestion_date=2026-05-07/pipeline_run_id=run-123/"
            "validation_results.json"
        ),
    )
    s3_objects[("bucket", validation_location.artifact_key)] = (
        validation_path.read_bytes()
    )
    for paths in manifests.values():
        for path in paths:
            path.unlink()
    validation_path.unlink()

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
        sba_7a_manifest_paths=manifest_locations["sba_7a"],
        sba_504_manifest_paths=manifest_locations["sba_504"],
        census_bds_manifest_paths=manifest_locations["census"],
        bls_laus_manifest_paths=manifest_locations["bls"],
        validation_result_paths=[validation_location],
        write_pandas_func=writer,
        s3_client=FakeS3Client(
            {
                "raw/sba/7a_504_foia/sba_7a.csv": "LoanNumber,GrossApproval\n",
                "raw/sba/7a_504_foia/sba_504.csv": "LoanNumber,GrossApproval\n",
            },
            objects=s3_objects,
        ),
    )

    assert summary.table_row_counts["RAW.RAW_INGESTION_MANIFEST"] == 4
    assert summary.table_row_counts["RAW.RAW_VALIDATION_RESULT"] == 1
    assert (
        writer.written_frames["RAW_INGESTION_MANIFEST"]["RAW_URI"]
        .str.startswith("s3://bucket/raw/")
        .all()
    )


def test_snowflake_csv_columns_are_stable_text_identifiers():
    """Validate that snowflake CSV columns are stable text identifiers."""
    assert snowflake_csv_columns(
        ["LocationID", "Gross Approval", "123 Code", "", "Gross-Approval"]
    ) == [
        "LOCATIONID",
        "GROSS_APPROVAL",
        "_123_CODE",
        "COLUMN_4",
        "GROSS_APPROVAL_2",
    ]


def test_snowflake_csv_columns_prevent_suffix_collisions():
    """Validate that snowflake CSV columns prevent suffix collisions."""
    assert snowflake_csv_columns(["A", "A", "A_2"]) == ["A", "A_2", "A_2_2"]


def test_snowflake_stage_setup_rejects_invalid_identifiers():
    """Validate that snowflake stage setup rejects invalid identifiers."""
    with pytest.raises(SnowflakeRawLoadError, match="Invalid Snowflake identifier"):
        create_s3_stage_load_objects(
            FakeSnowflakeConnection(),
            raw_schema="RAW;drop schema RAW",
            bucket="unit-test-bucket",
            stage_name="RAW_S3_STAGE",
            storage_integration=None,
        )


def test_snowflake_loader_blocks_failed_validation(tmp_path):
    """Validate that snowflake loader blocks failed validation."""
    manifests = build_raw_load_fixture_manifests(tmp_path)
    validation_path = write_validation_results(
        [raw_load_validation_result(status="failed")],
        tmp_path / "validation" / "validation_results.json",
    )

    with pytest.raises(SnowflakeRawLoadError, match="Critical raw validation failures"):
        load_raw_extracts_to_snowflake_from_s3(
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
            s3_client=FakeS3Client({}),
        )


def test_snowflake_loader_rejects_empty_required_manifest_group(tmp_path):
    """Validate that snowflake loader rejects empty required manifest group."""
    manifests = build_raw_load_fixture_manifests(tmp_path)
    validation_path = write_validation_results(
        [raw_load_validation_result()],
        tmp_path / "validation" / "validation_results.json",
    )

    with pytest.raises(SnowflakeRawLoadError, match="Required manifest group is empty"):
        load_raw_extracts_to_snowflake_from_s3(
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
            s3_client=FakeS3Client({}),
        )


def test_snowflake_loader_rejects_row_count_mismatch(tmp_path):
    """Validate that snowflake loader rejects row count mismatch."""
    manifests = build_raw_load_fixture_manifests(tmp_path)
    make_manifests_s3_backed(manifests)
    validation_path = write_validation_results(
        [raw_load_validation_result()],
        tmp_path / "validation" / "validation_results.json",
    )

    with pytest.raises(SnowflakeRawLoadError, match="Row count mismatch"):
        load_raw_extracts_to_snowflake_from_s3(
            connection=FakeSnowflakeConnection(
                table_counts={"RAW.RAW_SBA_7A_FOIA": 999}
            ),
            database="SMALL_BUSINESS_LENDING",
            raw_schema="RAW",
            audit_schema="AUDIT",
            sba_7a_manifest_paths=manifests["sba_7a"],
            sba_504_manifest_paths=manifests["sba_504"],
            census_bds_manifest_paths=manifests["census"],
            bls_laus_manifest_paths=manifests["bls"],
            validation_result_paths=[validation_path],
            write_pandas_func=FakeSnowflakeWriter(),
            s3_client=FakeS3Client(
                {"raw/sba/7a_504_foia/sba_7a.csv": "LoanNumber,GrossApproval\n"}
            ),
        )
