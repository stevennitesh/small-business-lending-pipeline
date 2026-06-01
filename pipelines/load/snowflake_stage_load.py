from __future__ import annotations

import re
from urllib.parse import urlparse

from pipelines.load.snowflake_errors import SnowflakeRawLoadError


_SNOWFLAKE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")
_S3_BUCKET_NAME = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")


def create_s3_stage_load_objects(
    connection,
    *,
    raw_schema: str,
    bucket: str,
    stage_name: str,
    storage_integration: str | None,
) -> None:
    raw_schema_sql = snowflake_identifier(raw_schema)
    stage_name_sql = snowflake_identifier(stage_name)
    stage_url_sql = snowflake_sql_literal(_s3_stage_url(bucket))
    integration_clause = (
        f"\n  storage_integration = {snowflake_identifier(storage_integration)}"
        if storage_integration
        else ""
    )
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            create or replace file format {raw_schema_sql}."RAW_CSV_LOAD_FORMAT"
              type = csv
              skip_header = 1
              field_optionally_enclosed_by = '"'
              escape_unenclosed_field = none
              trim_space = true
              null_if = ('', 'NULL', 'null')
              error_on_column_count_mismatch = false
            """
        )
        cursor.execute(
            f"""
            create or replace file format {raw_schema_sql}."RAW_JSON_FORMAT"
              type = json
              strip_outer_array = false
            """
        )
        cursor.execute(
            f"""
            create or replace stage {raw_schema_sql}.{stage_name_sql}
              url = {stage_url_sql}{integration_clause}
            """
        )


def snowflake_identifier(identifier: str) -> str:
    """Validate and quote a Snowflake identifier or dotted identifier path."""
    parts = str(identifier).split(".")
    if not parts or any(not _SNOWFLAKE_IDENTIFIER.fullmatch(part) for part in parts):
        raise SnowflakeRawLoadError(f"Invalid Snowflake identifier: {identifier}")
    return ".".join(f'"{part.upper()}"' for part in parts)


def snowflake_sql_literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _s3_stage_url(bucket_or_url: str) -> str:
    stage_url = (
        str(bucket_or_url)
        if str(bucket_or_url).startswith("s3://")
        else f"s3://{bucket_or_url}"
    )
    parsed_url = urlparse(stage_url)
    if parsed_url.scheme != "s3" or not _valid_s3_bucket(parsed_url.netloc):
        raise SnowflakeRawLoadError(f"Invalid S3 stage URL: {bucket_or_url}")
    return stage_url.rstrip("/")


def _valid_s3_bucket(bucket: str) -> bool:
    return (
        bool(_S3_BUCKET_NAME.fullmatch(bucket))
        and ".." not in bucket
        and ".-" not in bucket
        and "-." not in bucket
    )
