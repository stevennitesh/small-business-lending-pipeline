from __future__ import annotations


def create_s3_stage_load_objects(
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
              escape_unenclosed_field = none
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
