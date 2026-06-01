from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Any

import boto3

from pipelines.load.raw_load_metadata import (
    RAW_ROW_METADATA_COLUMNS,
    manifest_raw_row_metadata,
)
from pipelines.load.snowflake_errors import SnowflakeRawLoadError
from pipelines.load.snowflake_stage_load import (
    snowflake_identifier,
    snowflake_sql_literal,
)
from pipelines.storage.raw_artifacts import parse_s3_uri


RAW_METADATA_COLUMNS = {
    column_name.upper(): "varchar"
    for column_name in RAW_ROW_METADATA_COLUMNS
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


def load_s3_manifest_group(
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
    s3_client: Any | None,
) -> None:
    header = _csv_header_from_manifest(manifest, s3_client=s3_client)
    source_columns = {
        column_name: "varchar"
        for column_name in snowflake_csv_columns(header)
    }
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


def snowflake_csv_columns(header: list[str]) -> list[str]:
    if not header:
        raise SnowflakeRawLoadError("CSV source header is empty.")

    columns: list[str] = []
    seen: dict[str, int] = {}
    for index, raw_column in enumerate(header, start=1):
        normalized = _snowflake_identifier(raw_column)
        if not normalized:
            normalized = f"COLUMN_{index}"
        base_name = normalized
        suffix = seen.get(base_name, 1)
        while normalized in seen:
            suffix += 1
            normalized = f"{base_name}_{suffix}"
        seen[base_name] = suffix
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
    table_name_sql = _qualified_table_name(raw_schema, table_name)
    stage_path_prefix = _stage_path_prefix(raw_schema, stage_name)
    with connection.cursor() as cursor:
        for manifest in manifests:
            reference = parse_s3_uri(
                str(manifest.get("raw_uri") or manifest["s3_raw_uri"])
            )
            file_format = _csv_load_file_format(raw_schema)
            stage_path = snowflake_sql_literal(f"{stage_path_prefix}/{reference.key}")
            cursor.execute(
                f"""
                copy into {table_name_sql}
                from {stage_path}
                file_format = (format_name = {file_format})
                on_error = abort_statement
                """
            )
            cursor.execute(
                f"""
                update {table_name_sql}
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
        f"{snowflake_identifier(column_name)} {column_type}"
        for column_name, column_type in column_definitions.items()
    )
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            create or replace table {_qualified_table_name(raw_schema, table_name)} (
              {columns_sql}
            )
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
    table_name_sql = _qualified_table_name(raw_schema, table_name)
    landing_table_name_sql = _qualified_table_name(
        raw_schema,
        f"{table_name}_LANDING",
    )
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
            insert into {table_name_sql} (
              "YEAR", "NAME", "STATE", "ESTAB", "ESTABS_ENTRY",
              "ESTABS_ENTRY_RATE", "ESTABS_EXIT", "ESTABS_EXIT_RATE",
              "FIRM", "JOB_CREATION", "JOB_DESTRUCTION",
              {", ".join(RAW_ROW_METADATA_COLUMNS)}
            )
            select
              get(data_row, array_position(to_variant('YEAR'), headers))::varchar
                as "YEAR",
              get(data_row, array_position(to_variant('NAME'), headers))::varchar
                as "NAME",
              get(data_row, array_position(to_variant('state'), headers))::varchar
                as "STATE",
              get(data_row, array_position(to_variant('ESTAB'), headers))::varchar
                as "ESTAB",
              get(data_row, array_position(to_variant('ESTABS_ENTRY'), headers))::varchar
                as "ESTABS_ENTRY",
              get(data_row, array_position(to_variant('ESTABS_ENTRY_RATE'), headers))::varchar
                as "ESTABS_ENTRY_RATE",
              get(data_row, array_position(to_variant('ESTABS_EXIT'), headers))::varchar
                as "ESTABS_EXIT",
              get(data_row, array_position(to_variant('ESTABS_EXIT_RATE'), headers))::varchar
                as "ESTABS_EXIT_RATE",
              get(data_row, array_position(to_variant('FIRM'), headers))::varchar
                as "FIRM",
              get(data_row, array_position(to_variant('JOB_CREATION'), headers))::varchar
                as "JOB_CREATION",
              get(data_row, array_position(to_variant('JOB_DESTRUCTION'), headers))::varchar
                as "JOB_DESTRUCTION",
              {_metadata_select_list(manifest)}
            from (
              select
                PAYLOAD[0] as headers,
                flattened.value as data_row
              from {landing_table_name_sql},
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
    table_name_sql = _qualified_table_name(raw_schema, table_name)
    landing_table_name_sql = _qualified_table_name(
        raw_schema,
        f"{table_name}_LANDING",
    )
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
            insert into {table_name_sql} (
              "SERIES_ID", "STATE_FIPS", "STATE_ABBR", "STATE_NAME",
              "OBSERVED_MONTH", "VALUE", "YEAR", "PERIOD", "FOOTNOTES",
              {", ".join(RAW_ROW_METADATA_COLUMNS)}
            )
            select
              value:series_id::varchar as "SERIES_ID",
              value:state_fips::varchar as "STATE_FIPS",
              value:state_abbr::varchar as "STATE_ABBR",
              value:state_name::varchar as "STATE_NAME",
              value:observed_month::varchar as "OBSERVED_MONTH",
              value:value::varchar as "VALUE",
              value:year::varchar as "YEAR",
              value:period::varchar as "PERIOD",
              value:footnotes as "FOOTNOTES",
              {_metadata_select_list(manifest)}
            from {landing_table_name_sql},
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
    landing_table_name_sql = _qualified_table_name(raw_schema, f"{table_name}_LANDING")
    stage_path = snowflake_sql_literal(
        f"{_stage_path_prefix(raw_schema, stage_name)}/{reference.key}"
    )
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            create or replace temporary table {landing_table_name_sql} (
              "PAYLOAD" variant
            )
            """
        )
        cursor.execute(
            f"""
            copy into {landing_table_name_sql}
            from {stage_path}
            file_format = (format_name = {file_format})
            on_error = abort_statement
            """
        )


def _metadata_assignments(manifest: dict[str, Any]) -> str:
    return ", ".join(
        f"{snowflake_identifier(column_name)} = {_sql_literal(value)}"
        for column_name, value in _metadata_values(manifest).items()
    )


def _metadata_select_list(manifest: dict[str, Any]) -> str:
    return ", ".join(
        f"{_sql_literal(value)} as {snowflake_identifier(column_name)}"
        for column_name, value in _metadata_values(manifest).items()
    )


def _metadata_values(manifest: dict[str, Any]) -> dict[str, Any]:
    return manifest_raw_row_metadata(manifest, uppercase=True)


def _sql_literal(value: Any) -> str:
    if value is None:
        return "null"
    return "'" + str(value).replace("'", "''") + "'"


def _stage_file_format(raw_schema: str, file_format: str) -> str:
    if file_format.lower() == "csv":
        return _csv_load_file_format(raw_schema)
    if file_format.lower() == "json":
        return _qualified_table_name(raw_schema, "RAW_JSON_FORMAT")
    raise SnowflakeRawLoadError(f"Unsupported Snowflake S3 file format: {file_format}")


def _csv_load_file_format(raw_schema: str) -> str:
    return _qualified_table_name(raw_schema, "RAW_CSV_LOAD_FORMAT")


def _qualified_table_name(raw_schema: str, table_name: str) -> str:
    return f"{snowflake_identifier(raw_schema)}.{snowflake_identifier(table_name)}"


def _stage_path_prefix(raw_schema: str, stage_name: str) -> str:
    return f"@{snowflake_identifier(raw_schema)}.{snowflake_identifier(stage_name)}"
