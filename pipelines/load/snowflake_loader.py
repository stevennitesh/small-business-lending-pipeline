from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

import boto3
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

RAW_METADATA_COLUMNS = {
    "PIPELINE_RUN_ID": "varchar",
    "SOURCE_SYSTEM": "varchar",
    "SOURCE_DATASET": "varchar",
    "SOURCE_RESOURCE_NAME": "varchar",
    "INGESTION_DATE": "varchar",
    "STORAGE_BACKEND": "varchar",
    "RAW_URI": "varchar",
    "RAW_FILE_PATH": "varchar",
    "S3_RAW_URI": "varchar",
    "SHA256_CHECKSUM": "varchar",
}

CENSUS_BDS_RAW_COLUMNS = {
    "YEAR": "varchar",
    "NAME": "varchar",
    "STATE": "varchar",
    "ESTAB": "varchar",
    "ESTABS_ENTRY": "varchar",
    "ESTABS_ENTRY_RATE": "varchar",
    "ESTABS_EXIT": "varchar",
    "ESTABS_EXIT_RATE": "varchar",
    "FIRM": "varchar",
    "JOB_CREATION": "varchar",
    "JOB_DESTRUCTION": "varchar",
}

BLS_LAUS_RAW_COLUMNS = {
    "SERIES_ID": "varchar",
    "STATE_FIPS": "varchar",
    "STATE_ABBR": "varchar",
    "STATE_NAME": "varchar",
    "OBSERVED_MONTH": "varchar",
    "VALUE": "varchar",
    "YEAR": "varchar",
    "PERIOD": "varchar",
    "FOOTNOTES": "variant",
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
        load_dotenv(override=False)
        values = {
            "account": os.getenv("SNOWFLAKE_ACCOUNT"),
            "user": os.getenv("SNOWFLAKE_USER"),
            "password": os.getenv("SNOWFLAKE_PASSWORD"),
            "role": os.getenv("SNOWFLAKE_ROLE"),
            "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE"),
            "database": os.getenv("SNOWFLAKE_DATABASE"),
            "raw_schema": os.getenv(
                "SNOWFLAKE_RAW_SCHEMA",
                os.getenv("SNOWFLAKE_SCHEMA", "RAW"),
            ),
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
        return cls(
            account=str(values["account"]),
            user=str(values["user"]),
            password=str(values["password"]),
            role=str(values["role"]),
            warehouse=str(values["warehouse"]),
            database=str(values["database"]),
            raw_schema=str(values["raw_schema"]),
            audit_schema=str(values["audit_schema"]),
            storage_integration=(
                str(values["storage_integration"])
                if values["storage_integration"]
                else None
            ),
        )

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
    """Compatibility local-file loader; cloud flow uses the S3 loader."""

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
    _create_required_schemas(
        connection,
        raw_schema=raw_schema,
        audit_schema=audit_schema,
    )

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
    s3_client: Any | None = None,
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

    _create_required_schemas(
        connection,
        raw_schema=raw_schema,
        audit_schema=audit_schema,
    )
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
        _load_s3_manifest_group(
            connection,
            raw_schema=raw_schema,
            source_table=source_table,
            table_name=table_name,
            manifests=manifests,
            stage_name=stage_name,
            s3_client=s3_client,
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


def _create_required_schemas(
    connection,
    *,
    raw_schema: str = "RAW",
    audit_schema: str = "AUDIT",
) -> None:
    schema_names = {raw_schema, audit_schema}
    if raw_schema.upper() == "RAW" and audit_schema.upper() == "AUDIT":
        schema_names.update(REQUIRED_SCHEMAS)

    with connection.cursor() as cursor:
        for schema_name in sorted(schema_names):
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
            create or replace file format {raw_schema}.RAW_CSV_LOAD_FORMAT
              type = csv
              skip_header = 1
              field_optionally_enclosed_by = '"'
              trim_space = true
              null_if = ('', 'NULL', 'null')
              error_on_column_count_mismatch = false
            """
        )
        cursor.execute(
            f"""
            create or replace file format {raw_schema}.RAW_JSON_FORMAT
              type = json
              strip_outer_array = false
            """
        )
        cursor.execute(
            f"""
            create or replace stage {raw_schema}.{stage_name}
              url = 's3://{bucket}'{integration_clause}
            """
        )


def _load_s3_manifest_group(
    connection,
    *,
    raw_schema: str,
    source_table: str,
    table_name: str,
    manifests: list[dict[str, Any]],
    stage_name: str,
    s3_client: Any | None,
) -> None:
    if source_table in {"raw_sba_7a_foia", "raw_sba_504_foia"}:
        _create_csv_source_table_from_stage(
            connection=connection,
            raw_schema=raw_schema,
            table_name=table_name,
            manifest=manifests[0],
            stage_name=stage_name,
            s3_client=s3_client,
        )
        _copy_csv_manifest_group_from_stage(
            connection=connection,
            raw_schema=raw_schema,
            table_name=table_name,
            manifests=manifests,
            stage_name=stage_name,
        )
        return

    if source_table == "raw_census_bds_state_year":
        _create_explicit_source_table(
            connection=connection,
            raw_schema=raw_schema,
            table_name=table_name,
            source_columns=CENSUS_BDS_RAW_COLUMNS,
        )
        for manifest in manifests:
            _insert_census_bds_json_from_stage(
                connection=connection,
                raw_schema=raw_schema,
                table_name=table_name,
                manifest=manifest,
                stage_name=stage_name,
            )
        return

    if source_table == "raw_bls_laus_state_month":
        _create_explicit_source_table(
            connection=connection,
            raw_schema=raw_schema,
            table_name=table_name,
            source_columns=BLS_LAUS_RAW_COLUMNS,
        )
        for manifest in manifests:
            _insert_bls_laus_json_from_stage(
                connection=connection,
                raw_schema=raw_schema,
                table_name=table_name,
                manifest=manifest,
                stage_name=stage_name,
            )
        return

    raise SnowflakeRawLoadError(f"Unsupported Snowflake S3 source table: {source_table}")


def _create_csv_source_table_from_stage(
    *,
    connection,
    raw_schema: str,
    table_name: str,
    manifest: dict[str, Any],
    stage_name: str,
    s3_client: Any | None,
) -> None:
    del stage_name
    header = _csv_header_from_manifest(manifest, s3_client=s3_client)
    source_columns = {column_name: "varchar" for column_name in _snowflake_csv_columns(header)}
    _create_explicit_source_table(
        connection=connection,
        raw_schema=raw_schema,
        table_name=table_name,
        source_columns=source_columns,
    )


def _csv_header_from_manifest(
    manifest: dict[str, Any],
    *,
    s3_client: Any | None = None,
) -> list[str]:
    local_path = manifest.get("local_raw_path")
    if local_path:
        path = Path(local_path)
        if path.exists():
            with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
                return next(csv.reader(csv_file))

    raw_uri = str(manifest.get("raw_uri") or manifest["s3_raw_uri"])
    reference = parse_s3_uri(raw_uri)
    client = s3_client or boto3.client("s3")
    response = client.get_object(
        Bucket=reference.bucket,
        Key=reference.key,
        Range="bytes=0-65535",
    )
    header_chunk = response["Body"].read().decode("utf-8-sig", errors="replace")
    return next(csv.reader(io.StringIO(header_chunk)))


def _snowflake_csv_columns(header: list[str]) -> list[str]:
    if not header:
        raise SnowflakeRawLoadError("CSV source header is empty.")

    columns: list[str] = []
    seen: dict[str, int] = {}
    for index, raw_column in enumerate(header, start=1):
        normalized = _snowflake_identifier(raw_column)
        if not normalized:
            normalized = f"COLUMN_{index}"
        if normalized in seen:
            seen[normalized] += 1
            normalized = f"{normalized}_{seen[normalized]}"
        else:
            seen[normalized] = 1
        columns.append(normalized)
    return columns


def _snowflake_identifier(value: str) -> str:
    identifier = re.sub(r"[^0-9A-Za-z_]+", "_", value.strip()).strip("_").upper()
    identifier = re.sub(r"_+", "_", identifier)
    if identifier and identifier[0].isdigit():
        identifier = f"_{identifier}"
    return identifier


def _copy_csv_manifest_group_from_stage(
    connection,
    *,
    raw_schema: str,
    table_name: str,
    manifests: list[dict[str, Any]],
    stage_name: str,
) -> None:
    with connection.cursor() as cursor:
        for manifest in manifests:
            reference = parse_s3_uri(str(manifest.get("raw_uri") or manifest["s3_raw_uri"]))
            file_format = _csv_load_file_format(raw_schema)
            cursor.execute(
                f"""
                copy into {raw_schema}.{table_name}
                from @{raw_schema}.{stage_name}/{reference.key}
                file_format = (format_name = {file_format})
                on_error = abort_statement
                """
            )
            cursor.execute(
                f"""
                update {raw_schema}.{table_name}
                set {_metadata_assignments(manifest)}
                where RAW_URI is null
                """
            )


def _create_explicit_source_table(
    *,
    connection,
    raw_schema: str,
    table_name: str,
    source_columns: dict[str, str],
) -> None:
    column_definitions = {
        **source_columns,
        **RAW_METADATA_COLUMNS,
    }
    columns_sql = ",\n              ".join(
        f"{column_name} {column_type}"
        for column_name, column_type in column_definitions.items()
    )
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            create or replace table {raw_schema}.{table_name} (
              {columns_sql}
            )
            """
        )


def _add_metadata_columns(connection, *, raw_schema: str, table_name: str) -> None:
    with connection.cursor() as cursor:
        for column_name, column_type in RAW_METADATA_COLUMNS.items():
            cursor.execute(
                f"""
                alter table {raw_schema}.{table_name}
                add column if not exists {column_name} {column_type}
                """
            )


def _insert_census_bds_json_from_stage(
    *,
    connection,
    raw_schema: str,
    table_name: str,
    manifest: dict[str, Any],
    stage_name: str,
) -> None:
    _copy_json_payload_to_landing(
        connection=connection,
        raw_schema=raw_schema,
        table_name=table_name,
        manifest=manifest,
        stage_name=stage_name,
    )
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            insert into {raw_schema}.{table_name} (
              YEAR, NAME, STATE, ESTAB, ESTABS_ENTRY, ESTABS_ENTRY_RATE,
              ESTABS_EXIT, ESTABS_EXIT_RATE, FIRM, JOB_CREATION, JOB_DESTRUCTION,
              {", ".join(RAW_METADATA_COLUMNS)}
            )
            select
              get(data_row, array_position(to_variant('YEAR'), headers))::varchar as YEAR,
              get(data_row, array_position(to_variant('NAME'), headers))::varchar as NAME,
              get(data_row, array_position(to_variant('state'), headers))::varchar as STATE,
              get(data_row, array_position(to_variant('ESTAB'), headers))::varchar as ESTAB,
              get(data_row, array_position(to_variant('ESTABS_ENTRY'), headers))::varchar as ESTABS_ENTRY,
              get(data_row, array_position(to_variant('ESTABS_ENTRY_RATE'), headers))::varchar as ESTABS_ENTRY_RATE,
              get(data_row, array_position(to_variant('ESTABS_EXIT'), headers))::varchar as ESTABS_EXIT,
              get(data_row, array_position(to_variant('ESTABS_EXIT_RATE'), headers))::varchar as ESTABS_EXIT_RATE,
              get(data_row, array_position(to_variant('FIRM'), headers))::varchar as FIRM,
              get(data_row, array_position(to_variant('JOB_CREATION'), headers))::varchar as JOB_CREATION,
              get(data_row, array_position(to_variant('JOB_DESTRUCTION'), headers))::varchar as JOB_DESTRUCTION,
              {_metadata_select_list(manifest)}
            from (
              select
                PAYLOAD[0] as headers,
                flattened.value as data_row
              from {raw_schema}.{table_name}_LANDING,
                lateral flatten(input => PAYLOAD) as flattened
              where flattened.index > 0
            )
            """
        )


def _insert_bls_laus_json_from_stage(
    *,
    connection,
    raw_schema: str,
    table_name: str,
    manifest: dict[str, Any],
    stage_name: str,
) -> None:
    _copy_json_payload_to_landing(
        connection=connection,
        raw_schema=raw_schema,
        table_name=table_name,
        manifest=manifest,
        stage_name=stage_name,
    )
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            insert into {raw_schema}.{table_name} (
              SERIES_ID, STATE_FIPS, STATE_ABBR, STATE_NAME, OBSERVED_MONTH,
              VALUE, YEAR, PERIOD, FOOTNOTES, {", ".join(RAW_METADATA_COLUMNS)}
            )
            select
              value:series_id::varchar as SERIES_ID,
              value:state_fips::varchar as STATE_FIPS,
              value:state_abbr::varchar as STATE_ABBR,
              value:state_name::varchar as STATE_NAME,
              value:observed_month::varchar as OBSERVED_MONTH,
              value:value::varchar as VALUE,
              value:year::varchar as YEAR,
              value:period::varchar as PERIOD,
              value:footnotes as FOOTNOTES,
              {_metadata_select_list(manifest)}
            from {raw_schema}.{table_name}_LANDING,
              lateral flatten(input => PAYLOAD:normalized_rows)
            """
        )


def _copy_json_payload_to_landing(
    *,
    connection,
    raw_schema: str,
    table_name: str,
    manifest: dict[str, Any],
    stage_name: str,
) -> None:
    reference = parse_s3_uri(str(manifest.get("raw_uri") or manifest["s3_raw_uri"]))
    file_format = _stage_file_format(raw_schema, str(manifest["file_format"]))
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            create or replace temporary table {raw_schema}.{table_name}_LANDING (
              PAYLOAD variant
            )
            """
        )
        cursor.execute(
            f"""
            copy into {raw_schema}.{table_name}_LANDING
            from @{raw_schema}.{stage_name}/{reference.key}
            file_format = (format_name = {file_format})
            on_error = abort_statement
            """
        )


def _metadata_assignments(manifest: dict[str, Any]) -> str:
    return ", ".join(
        f"{column_name} = {_sql_literal(value)}"
        for column_name, value in _metadata_values(manifest).items()
    )


def _metadata_select_list(manifest: dict[str, Any]) -> str:
    return ", ".join(
        f"{_sql_literal(value)} as {column_name}"
        for column_name, value in _metadata_values(manifest).items()
    )


def _metadata_values(manifest: dict[str, Any]) -> dict[str, Any]:
    local_raw_path = manifest.get("local_raw_path")
    raw_uri = manifest.get("raw_uri") or manifest.get("s3_raw_uri") or local_raw_path
    return {
        "PIPELINE_RUN_ID": manifest["pipeline_run_id"],
        "SOURCE_SYSTEM": manifest["source_system"],
        "SOURCE_DATASET": manifest["dataset_name"],
        "SOURCE_RESOURCE_NAME": manifest["resource_name"],
        "INGESTION_DATE": manifest["ingestion_date"],
        "STORAGE_BACKEND": manifest.get("storage_backend") or "s3",
        "RAW_URI": raw_uri,
        "RAW_FILE_PATH": local_raw_path or raw_uri,
        "S3_RAW_URI": manifest["s3_raw_uri"],
        "SHA256_CHECKSUM": manifest["sha256_checksum"],
    }


def _sql_literal(value: Any) -> str:
    if value is None:
        return "null"
    return "'" + str(value).replace("'", "''") + "'"


def _stage_file_format(raw_schema: str, file_format: str) -> str:
    if file_format.lower() == "csv":
        return _csv_load_file_format(raw_schema)
    if file_format.lower() == "json":
        return f"{raw_schema}.RAW_JSON_FORMAT"
    raise SnowflakeRawLoadError(f"Unsupported Snowflake S3 file format: {file_format}")


def _csv_load_file_format(raw_schema: str) -> str:
    return f"{raw_schema}.RAW_CSV_LOAD_FORMAT"


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
