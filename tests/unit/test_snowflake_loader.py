from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from pipelines.load.snowflake_loader import (
    REQUIRED_SCHEMAS,
    SNOWFLAKE_RAW_TABLES,
    SnowflakeConfig,
    SnowflakeRawLoadError,
    _snowflake_csv_columns,
    load_raw_extracts_to_snowflake_from_s3,
)
from pipelines.storage.raw_artifacts import ArtifactLocation
from pipelines.utils.hashing import calculate_sha256, hash_schema
from pipelines.validation.validation_result import (
    ValidationResult,
    write_validation_results,
)


def test_snowflake_config_supports_isolated_raw_schema(monkeypatch):
    monkeypatch.setenv("SNOWFLAKE_ACCOUNT", "acct")
    monkeypatch.setenv("SNOWFLAKE_USER", "user")
    monkeypatch.setenv("SNOWFLAKE_PASSWORD", "password")
    monkeypatch.setenv("SNOWFLAKE_ROLE", "role")
    monkeypatch.setenv("SNOWFLAKE_WAREHOUSE", "warehouse")
    monkeypatch.setenv("SNOWFLAKE_DATABASE", "database")
    monkeypatch.setenv("SNOWFLAKE_SCHEMA", "RAW")
    monkeypatch.setenv("SNOWFLAKE_RAW_SCHEMA", "SMOKE_RAW")
    monkeypatch.setenv("SNOWFLAKE_STORAGE_INTEGRATION", "")

    config = SnowflakeConfig.from_env()

    assert config.raw_schema == "SMOKE_RAW"
    assert config.storage_integration is None


def test_snowflake_config_prefers_route_neutral_raw_schema(monkeypatch):
    monkeypatch.setenv("SNOWFLAKE_ACCOUNT", "acct")
    monkeypatch.setenv("SNOWFLAKE_USER", "user")
    monkeypatch.setenv("SNOWFLAKE_PASSWORD", "password")
    monkeypatch.setenv("SNOWFLAKE_ROLE", "role")
    monkeypatch.setenv("SNOWFLAKE_WAREHOUSE", "warehouse")
    monkeypatch.setenv("SNOWFLAKE_DATABASE", "database")
    monkeypatch.setenv("SNOWFLAKE_SCHEMA", "RAW")
    monkeypatch.setenv("SNOWFLAKE_RAW_SCHEMA", "SMOKE_RAW")
    monkeypatch.setenv("RAW_SCHEMA", "ROUTE_RAW")

    config = SnowflakeConfig.from_env()

    assert config.raw_schema == "ROUTE_RAW"


def test_snowflake_s3_loader_uses_stage_copy_and_writes_metadata(tmp_path):
    manifests = _build_fixture_manifests(tmp_path)
    sba_7a_part2 = tmp_path / "raw" / "sba_7a_part2.csv"
    sba_7a_part2.write_text("LoanNumber,GrossApproval\n4,4000\n", encoding="utf-8")
    manifests["sba_7a"].append(
        _write_manifest(
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
    _make_manifests_s3_backed(manifests)
    validation_path = write_validation_results(
        [_validation_result()],
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
    assert "create or replace file format RAW.RAW_CSV_LOAD_FORMAT" in sql
    assert "create or replace file format RAW.RAW_JSON_FORMAT" in sql
    assert "create or replace stage RAW.RAW_S3_STAGE" in sql
    assert "storage_integration = SBL_S3_INT" in sql
    assert "escape_unenclosed_field = none" in sql
    assert "error_on_column_count_mismatch = false" in sql
    assert "create or replace table RAW.RAW_SBA_7A_FOIA (" in sql
    assert "LOANNUMBER varchar" in sql
    assert "GROSSAPPROVAL varchar" in sql
    assert "using template" not in sql
    assert "RAW_URI varchar" in sql
    assert "update RAW.RAW_SBA_7A_FOIA set" in sql
    assert "STORAGE_BACKEND = 's3'" in sql
    assert "lateral flatten(input => PAYLOAD)" in sql
    assert "array_position(to_variant('YEAR'), headers)" in sql
    assert "array_position(to_variant('state'), headers)" in sql
    assert "lateral flatten(input => PAYLOAD:normalized_rows)" in sql
    assert "row.value" not in sql
    assert "RAW_URI = 's3://bucket/raw/sba/7a_504_foia/sba_7a.csv'" in sql
    assert "RAW_URI = 's3://bucket/raw/sba/7a_504_foia/sba_7a_part2.csv'" in sql
    first_copy = sql.index("@RAW.RAW_S3_STAGE/raw/sba/7a_504_foia/sba_7a.csv")
    first_update = sql.index("SOURCE_RESOURCE_NAME = 'sba_7a_fy2020_present'")
    second_copy = sql.index("@RAW.RAW_S3_STAGE/raw/sba/7a_504_foia/sba_7a_part2.csv")
    second_update = sql.index("SOURCE_RESOURCE_NAME = 'sba_7a_fy2000_fy2009'")
    assert first_copy < first_update < second_copy < second_update
    assert "create or replace table RAW.RAW_CENSUS_BDS_STATE_YEAR" in sql
    assert "insert into RAW.RAW_CENSUS_BDS_STATE_YEAR" in sql
    assert "create or replace table RAW.RAW_BLS_LAUS_STATE_MONTH" in sql
    assert "insert into RAW.RAW_BLS_LAUS_STATE_MONTH" in sql
    assert any(
        statement.startswith("copy into RAW.RAW_SBA_7A_FOIA")
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
    manifests = _build_fixture_manifests(tmp_path)
    _make_manifests_s3_backed(manifests)
    validation_path = write_validation_results(
        [_validation_result()],
        tmp_path / "validation" / "validation_results.json",
    )
    manifest_locations, s3_objects = _manifest_artifact_locations(manifests)
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
    assert writer.written_frames["RAW_INGESTION_MANIFEST"]["RAW_URI"].str.startswith(
        "s3://bucket/raw/"
    ).all()


def test_snowflake_csv_columns_are_stable_text_identifiers():
    assert _snowflake_csv_columns(
        ["LocationID", "Gross Approval", "123 Code", "", "Gross-Approval"]
    ) == [
        "LOCATIONID",
        "GROSS_APPROVAL",
        "_123_CODE",
        "COLUMN_4",
        "GROSS_APPROVAL_2",
    ]


def test_snowflake_loader_blocks_failed_validation(tmp_path):
    manifests = _build_fixture_manifests(tmp_path)
    validation_path = write_validation_results(
        [_validation_result(status="failed")],
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
    manifests = _build_fixture_manifests(tmp_path)
    validation_path = write_validation_results(
        [_validation_result()],
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
    manifests = _build_fixture_manifests(tmp_path)
    _make_manifests_s3_backed(manifests)
    validation_path = write_validation_results(
        [_validation_result()],
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


class FakeS3Client:
    def __init__(
        self,
        headers: dict[str, str],
        *,
        objects: dict[tuple[str, str], bytes] | None = None,
    ) -> None:
        self.headers = headers
        self.objects = objects or {}

    def get_object(self, **kwargs):
        object_key = (kwargs["Bucket"], kwargs["Key"])
        if object_key in self.objects:
            return {"Body": FakeBody(self.objects[object_key])}
        return {"Body": FakeBody(self.headers[kwargs["Key"]].encode("utf-8"))}


class FakeBody:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def read(self) -> bytes:
        return self.body


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


def _manifest_artifact_locations(
    manifests: dict[str, list[Path]],
) -> tuple[dict[str, list[ArtifactLocation]], dict[tuple[str, str], bytes]]:
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
