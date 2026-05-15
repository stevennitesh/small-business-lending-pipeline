from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

import pandas as pd
import snowflake.connector
from dotenv import load_dotenv
from snowflake.connector.pandas_tools import write_pandas

from pipelines.load.raw_load_common import (
    assert_validation_passed,
    flatten_manifest_groups,
    load_manifests,
    load_source_frame,
    load_validation_results,
    normalize_records,
    pipeline_run_ids_from_manifest_groups,
    require_manifest_groups,
)
from pipelines.storage.raw_artifacts import parse_s3_uri
from pipelines.utils.dates import utc_now_iso


REQUIRED_SCHEMAS = ("RAW", "STAGING", "INTERMEDIATE", "MARTS", "BI", "AUDIT")

SNOWFLAKE_RAW_TABLES = {
    "raw_sba_7a_foia": "RAW_SBA_7A_FOIA",
    "raw_sba_504_foia": "RAW_SBA_504_FOIA",
    "raw_census_bds_state_year": "RAW_CENSUS_BDS_STATE_YEAR",
    "raw_bls_laus_state_month": "RAW_BLS_LAUS_STATE_MONTH",
    "raw_ingestion_manifest": "RAW_INGESTION_MANIFEST",
    "raw_validation_result": "RAW_VALIDATION_RESULT",
    "raw_pipeline_run_summary": "RAW_PIPELINE_RUN_SUMMARY",
}

SOURCE_TABLES = {
    "raw_sba_7a_foia": "sba_7a",
    "raw_sba_504_foia": "sba_504",
    "raw_census_bds_state_year": "census_bds",
    "raw_bls_laus_state_month": "bls_laus",
}


class SnowflakeRawLoadError(RuntimeError):
    pass


@dataclass(frozen=True)
class SnowflakeConfig:
    account: str
    user: str
    password: str
    role: str
    warehouse: str
    database: str
    raw_schema: str = "RAW"
    audit_schema: str = "AUDIT"
    storage_integration: str | None = None

    @classmethod
    def from_env(cls) -> "SnowflakeConfig":
        load_dotenv(override=True)
        values = {
            "account": os.getenv("SNOWFLAKE_ACCOUNT"),
            "user": os.getenv("SNOWFLAKE_USER"),
            "password": os.getenv("SNOWFLAKE_PASSWORD"),
            "role": os.getenv("SNOWFLAKE_ROLE"),
            "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE"),
            "database": os.getenv("SNOWFLAKE_DATABASE"),
            "raw_schema": os.getenv("SNOWFLAKE_SCHEMA", "RAW"),
            "audit_schema": os.getenv("SNOWFLAKE_AUDIT_SCHEMA", "AUDIT"),
            "storage_integration": os.getenv("SNOWFLAKE_STORAGE_INTEGRATION"),
        }
        missing = sorted(
            key.upper()
            for key, value in values.items()
            if key not in {"raw_schema", "audit_schema", "storage_integration"}
            and not value
        )
        if missing:
            raise SnowflakeRawLoadError(
                "Missing Snowflake environment variables: "
                + ", ".join(f"SNOWFLAKE_{name}" for name in missing)
            )
        return cls(**{key: str(value) for key, value in values.items()})

    def connect_kwargs(self) -> dict[str, str]:
        return {
            "account": self.account,
            "user": self.user,
            "password": self.password,
            "role": self.role,
            "warehouse": self.warehouse,
            "database": self.database,
            "schema": self.raw_schema,
        }


@dataclass(frozen=True)
class SnowflakeRawLoadSummary:
    database: str
    raw_schema: str
    audit_schema: str
    table_row_counts: dict[str, int]
    pipeline_run_ids: tuple[str, ...]
    loaded_at_utc: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


WritePandasFunc = Callable[..., tuple[bool, int, int, list[Any]]]


def connect_to_snowflake(config: SnowflakeConfig):
    return snowflake.connector.connect(**config.connect_kwargs())


def load_raw_extracts_to_snowflake(
    *,
    connection,
    database: str,
    raw_schema: str = "RAW",
    audit_schema: str = "AUDIT",
    sba_7a_manifest_paths: Iterable[Path | str],
    sba_504_manifest_paths: Iterable[Path | str],
    census_bds_manifest_paths: Iterable[Path | str],
    bls_laus_manifest_paths: Iterable[Path | str],
    validation_result_paths: Iterable[Path | str],
    write_pandas_func: WritePandasFunc = write_pandas,
) -> SnowflakeRawLoadSummary:
    validation_results = load_validation_results(
        validation_result_paths,
        error_cls=SnowflakeRawLoadError,
        missing_message="At least one validation result file is required.",
    )
    assert_validation_passed(validation_results, error_cls=SnowflakeRawLoadError)

    manifest_groups = {
        "raw_sba_7a_foia": load_manifests(sba_7a_manifest_paths),
        "raw_sba_504_foia": load_manifests(sba_504_manifest_paths),
        "raw_census_bds_state_year": load_manifests(census_bds_manifest_paths),
        "raw_bls_laus_state_month": load_manifests(bls_laus_manifest_paths),
    }
    require_manifest_groups(manifest_groups, error_cls=SnowflakeRawLoadError)
    pipeline_run_ids = pipeline_run_ids_from_manifest_groups(manifest_groups)
    _create_required_schemas(connection)

    table_row_counts: dict[str, int] = {}
    for source_table, manifests in manifest_groups.items():
        frame = _snowflake_frame(
            load_source_frame(
                source_table,
                manifests,
                error_cls=SnowflakeRawLoadError,
            )
        )
        table_name = SNOWFLAKE_RAW_TABLES[source_table]
        _write_frame(
            connection=connection,
            frame=frame,
            database=database,
            schema=raw_schema,
            table_name=table_name,
            write_pandas_func=write_pandas_func,
        )
        row_count = len(frame)
        expected_row_count = sum(int(manifest["row_count"]) for manifest in manifests)
        if row_count != expected_row_count:
            raise SnowflakeRawLoadError(
                f"Row count mismatch for {raw_schema}.{table_name}: "
                f"loaded {row_count}, expected {expected_row_count}"
            )
        table_row_counts[f"{raw_schema}.{table_name}"] = row_count

    manifest_frame = _snowflake_frame(
        normalize_records(flatten_manifest_groups(manifest_groups))
    )
    _write_frame(
        connection=connection,
        frame=manifest_frame,
        database=database,
        schema=raw_schema,
        table_name=SNOWFLAKE_RAW_TABLES["raw_ingestion_manifest"],
        write_pandas_func=write_pandas_func,
    )
    table_row_counts[f"{raw_schema}.{SNOWFLAKE_RAW_TABLES['raw_ingestion_manifest']}"] = len(
        manifest_frame
    )

    validation_frame = normalize_records(
        [result.to_dict() for result in validation_results]
    )
    for column_name in ("expected_value", "observed_value"):
        validation_frame[column_name] = validation_frame[column_name].map(
            _snowflake_cell_value
        )
    validation_frame = _snowflake_frame(validation_frame)
    _write_frame(
        connection=connection,
        frame=validation_frame,
        database=database,
        schema=raw_schema,
        table_name=SNOWFLAKE_RAW_TABLES["raw_validation_result"],
        write_pandas_func=write_pandas_func,
    )
    table_row_counts[f"{raw_schema}.{SNOWFLAKE_RAW_TABLES['raw_validation_result']}"] = len(
        validation_frame
    )

    loaded_at_utc = utc_now_iso()
    summary_frame = _snowflake_frame(
        pd.DataFrame(
            [
                {
                    "pipeline_run_ids": ",".join(pipeline_run_ids),
                    "loaded_at_utc": loaded_at_utc,
                    "raw_table_count": len(SOURCE_TABLES),
                    "validation_status": "passed",
                    "load_pattern": "python_connector_fallback",
                }
            ]
        )
    )
    _write_frame(
        connection=connection,
        frame=summary_frame,
        database=database,
        schema=raw_schema,
        table_name=SNOWFLAKE_RAW_TABLES["raw_pipeline_run_summary"],
        write_pandas_func=write_pandas_func,
    )
    table_row_counts[
        f"{raw_schema}.{SNOWFLAKE_RAW_TABLES['raw_pipeline_run_summary']}"
    ] = len(summary_frame)

    return SnowflakeRawLoadSummary(
        database=database,
        raw_schema=raw_schema,
        audit_schema=audit_schema,
        table_row_counts=table_row_counts,
        pipeline_run_ids=pipeline_run_ids,
        loaded_at_utc=loaded_at_utc,
    )


def load_raw_extracts_to_snowflake_from_s3(
    *,
    connection,
    database: str,
    raw_schema: str = "RAW",
    audit_schema: str = "AUDIT",
    sba_7a_manifest_paths: Iterable[Path | str],
    sba_504_manifest_paths: Iterable[Path | str],
    census_bds_manifest_paths: Iterable[Path | str],
    bls_laus_manifest_paths: Iterable[Path | str],
    validation_result_paths: Iterable[Path | str],
    write_pandas_func: WritePandasFunc = write_pandas,
    stage_name: str = "RAW_S3_STAGE",
    storage_integration: str | None = None,
) -> SnowflakeRawLoadSummary:
    validation_results = load_validation_results(
        validation_result_paths,
        error_cls=SnowflakeRawLoadError,
        missing_message="At least one validation result file is required.",
    )
    assert_validation_passed(validation_results, error_cls=SnowflakeRawLoadError)

    manifest_groups = {
        "raw_sba_7a_foia": load_manifests(sba_7a_manifest_paths),
        "raw_sba_504_foia": load_manifests(sba_504_manifest_paths),
        "raw_census_bds_state_year": load_manifests(census_bds_manifest_paths),
        "raw_bls_laus_state_month": load_manifests(bls_laus_manifest_paths),
    }
    require_manifest_groups(manifest_groups, error_cls=SnowflakeRawLoadError)
    _require_s3_backed_manifests(manifest_groups)
    pipeline_run_ids = pipeline_run_ids_from_manifest_groups(manifest_groups)
    bucket = _single_s3_bucket(manifest_groups)

    _create_required_schemas(connection)
    _create_s3_stage_load_objects(
        connection,
        raw_schema=raw_schema,
        bucket=bucket,
        stage_name=stage_name,
        storage_integration=storage_integration,
    )

    table_row_counts: dict[str, int] = {}
    for source_table, manifests in manifest_groups.items():
        table_name = SNOWFLAKE_RAW_TABLES[source_table]
        _copy_manifest_group_from_stage(
            connection,
            raw_schema=raw_schema,
            table_name=table_name,
            manifests=manifests,
            stage_name=stage_name,
        )
        expected_row_count = sum(int(manifest["row_count"]) for manifest in manifests)
        row_count = _snowflake_table_count(connection, raw_schema, table_name)
        if row_count != expected_row_count:
            raise SnowflakeRawLoadError(
                f"Row count mismatch for {raw_schema}.{table_name}: "
                f"loaded {row_count}, expected {expected_row_count}"
            )
        table_row_counts[f"{raw_schema}.{table_name}"] = row_count

    loaded_at_utc = utc_now_iso()
    _write_raw_metadata_tables(
        connection=connection,
        database=database,
        raw_schema=raw_schema,
        manifest_groups=manifest_groups,
        validation_results=validation_results,
        pipeline_run_ids=pipeline_run_ids,
        loaded_at_utc=loaded_at_utc,
        load_pattern="s3_stage_copy",
        table_row_counts=table_row_counts,
        write_pandas_func=write_pandas_func,
    )

    return SnowflakeRawLoadSummary(
        database=database,
        raw_schema=raw_schema,
        audit_schema=audit_schema,
        table_row_counts=table_row_counts,
        pipeline_run_ids=pipeline_run_ids,
        loaded_at_utc=loaded_at_utc,
    )


def _create_required_schemas(connection) -> None:
    with connection.cursor() as cursor:
        for schema_name in REQUIRED_SCHEMAS:
            cursor.execute(f"create schema if not exists {schema_name}")


def _require_s3_backed_manifests(manifest_groups: dict[str, list[dict[str, Any]]]) -> None:
    non_s3_resources = [
        str(manifest.get("resource_name"))
        for manifests in manifest_groups.values()
        for manifest in manifests
        if str(manifest.get("storage_backend", "local")).lower() != "s3"
    ]
    if non_s3_resources:
        raise SnowflakeRawLoadError(
            "Snowflake S3 raw load requires S3-backed manifests: "
            + ", ".join(sorted(non_s3_resources))
        )


def _single_s3_bucket(manifest_groups: dict[str, list[dict[str, Any]]]) -> str:
    buckets = {
        parse_s3_uri(str(manifest.get("raw_uri") or manifest["s3_raw_uri"])).bucket
        for manifests in manifest_groups.values()
        for manifest in manifests
    }
    if len(buckets) != 1:
        raise SnowflakeRawLoadError(
            "Snowflake S3 raw load requires one S3 bucket, found: "
            + ", ".join(sorted(buckets))
        )
    return next(iter(buckets))


def _create_s3_stage_load_objects(
    connection,
    *,
    raw_schema: str,
    bucket: str,
    stage_name: str,
    storage_integration: str | None,
) -> None:
    integration_clause = (
        f"\n  storage_integration = {storage_integration}"
        if storage_integration
        else ""
    )
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            create file format if not exists {raw_schema}.RAW_CSV_FORMAT
              type = csv
              parse_header = true
              field_optionally_enclosed_by = '"'
              trim_space = true
              null_if = ('', 'NULL', 'null')
            """
        )
        cursor.execute(
            f"""
            create file format if not exists {raw_schema}.RAW_JSON_FORMAT
              type = json
              strip_outer_array = false
            """
        )
        cursor.execute(
            f"""
            create stage if not exists {raw_schema}.{stage_name}
              url = 's3://{bucket}'{integration_clause}
            """
        )


def _copy_manifest_group_from_stage(
    connection,
    *,
    raw_schema: str,
    table_name: str,
    manifests: list[dict[str, Any]],
    stage_name: str,
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(f"truncate table if exists {raw_schema}.{table_name}")
        for manifest in manifests:
            reference = parse_s3_uri(str(manifest.get("raw_uri") or manifest["s3_raw_uri"]))
            file_format = _stage_file_format(raw_schema, str(manifest["file_format"]))
            cursor.execute(
                f"""
                copy into {raw_schema}.{table_name}
                from @{raw_schema}.{stage_name}/{reference.key}
                file_format = (format_name = {file_format})
                match_by_column_name = case_insensitive
                on_error = abort_statement
                """
            )


def _stage_file_format(raw_schema: str, file_format: str) -> str:
    if file_format.lower() == "csv":
        return f"{raw_schema}.RAW_CSV_FORMAT"
    if file_format.lower() == "json":
        return f"{raw_schema}.RAW_JSON_FORMAT"
    raise SnowflakeRawLoadError(f"Unsupported Snowflake S3 file format: {file_format}")


def _snowflake_table_count(connection, raw_schema: str, table_name: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute(f"select count(*) from {raw_schema}.{table_name}")
        row = cursor.fetchone()
    return int(row[0])


def _write_raw_metadata_tables(
    *,
    connection,
    database: str,
    raw_schema: str,
    manifest_groups: dict[str, list[dict[str, Any]]],
    validation_results,
    pipeline_run_ids: tuple[str, ...],
    loaded_at_utc: str,
    load_pattern: str,
    table_row_counts: dict[str, int],
    write_pandas_func: WritePandasFunc,
) -> None:
    manifest_frame = _snowflake_frame(
        normalize_records(flatten_manifest_groups(manifest_groups))
    )
    _write_frame(
        connection=connection,
        frame=manifest_frame,
        database=database,
        schema=raw_schema,
        table_name=SNOWFLAKE_RAW_TABLES["raw_ingestion_manifest"],
        write_pandas_func=write_pandas_func,
    )
    table_row_counts[f"{raw_schema}.{SNOWFLAKE_RAW_TABLES['raw_ingestion_manifest']}"] = len(
        manifest_frame
    )

    validation_frame = normalize_records(
        [result.to_dict() for result in validation_results]
    )
    for column_name in ("expected_value", "observed_value"):
        validation_frame[column_name] = validation_frame[column_name].map(
            _snowflake_cell_value
        )
    validation_frame = _snowflake_frame(validation_frame)
    _write_frame(
        connection=connection,
        frame=validation_frame,
        database=database,
        schema=raw_schema,
        table_name=SNOWFLAKE_RAW_TABLES["raw_validation_result"],
        write_pandas_func=write_pandas_func,
    )
    table_row_counts[f"{raw_schema}.{SNOWFLAKE_RAW_TABLES['raw_validation_result']}"] = len(
        validation_frame
    )

    summary_frame = _snowflake_frame(
        pd.DataFrame(
            [
                {
                    "pipeline_run_ids": ",".join(pipeline_run_ids),
                    "loaded_at_utc": loaded_at_utc,
                    "raw_table_count": len(SOURCE_TABLES),
                    "validation_status": "passed",
                    "load_pattern": load_pattern,
                }
            ]
        )
    )
    _write_frame(
        connection=connection,
        frame=summary_frame,
        database=database,
        schema=raw_schema,
        table_name=SNOWFLAKE_RAW_TABLES["raw_pipeline_run_summary"],
        write_pandas_func=write_pandas_func,
    )
    table_row_counts[
        f"{raw_schema}.{SNOWFLAKE_RAW_TABLES['raw_pipeline_run_summary']}"
    ] = len(summary_frame)


def _write_frame(
    *,
    connection,
    frame: pd.DataFrame,
    database: str,
    schema: str,
    table_name: str,
    write_pandas_func: WritePandasFunc,
) -> None:
    success, _, _, output = write_pandas_func(
        connection,
        frame,
        table_name,
        database=database,
        schema=schema,
        auto_create_table=True,
        overwrite=True,
        quote_identifiers=False,
    )
    if not success:
        raise SnowflakeRawLoadError(f"Snowflake write failed for {schema}.{table_name}: {output}")


def _snowflake_frame(frame: pd.DataFrame) -> pd.DataFrame:
    snowflake_frame = frame.copy()
    for column_name in snowflake_frame.select_dtypes(include=["object"]).columns:
        snowflake_frame[column_name] = snowflake_frame[column_name].map(
            _snowflake_cell_value
        )
    snowflake_frame.columns = [str(column).upper() for column in snowflake_frame.columns]
    return snowflake_frame


def _snowflake_cell_value(value: Any) -> str | None:
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    if pd.isna(value):
        return None
    return str(value)


def main() -> None:
    parser = argparse.ArgumentParser(description="Load validated raw artifacts into Snowflake.")
    parser.add_argument("--sba-7a-manifest-path", action="append", required=True)
    parser.add_argument("--sba-504-manifest-path", action="append", required=True)
    parser.add_argument("--census-bds-manifest-path", action="append", required=True)
    parser.add_argument("--bls-laus-manifest-path", action="append", required=True)
    parser.add_argument("--validation-result-path", action="append", required=True)
    args = parser.parse_args()

    config = SnowflakeConfig.from_env()
    connection = connect_to_snowflake(config)
    try:
        summary = load_raw_extracts_to_snowflake(
            connection=connection,
            database=config.database,
            raw_schema=config.raw_schema,
            audit_schema=config.audit_schema,
            sba_7a_manifest_paths=args.sba_7a_manifest_path,
            sba_504_manifest_paths=args.sba_504_manifest_path,
            census_bds_manifest_paths=args.census_bds_manifest_path,
            bls_laus_manifest_paths=args.bls_laus_manifest_path,
            validation_result_paths=args.validation_result_path,
        )
    finally:
        connection.close()
    print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
