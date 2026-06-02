from __future__ import annotations

import json
from typing import Any, Callable

import pandas as pd

from pipelines.load.raw_load_metadata import raw_load_metadata_frames
from pipelines.load.snowflake_errors import SnowflakeRawLoadError


WritePandasFunc = Callable[..., tuple[bool, int, int, list[Any]]]


def write_raw_metadata_tables(
    *,
    connection,
    database: str,
    raw_schema: str,
    raw_table_names: dict[str, str],
    manifest_groups: dict[str, list[dict[str, Any]]],
    validation_results,
    pipeline_run_ids: tuple[str, ...],
    loaded_at_utc: str,
    load_pattern: str,
    table_row_counts: dict[str, int],
    write_pandas_func: WritePandasFunc,
) -> None:
    """Write raw-load metadata frames into Snowflake metadata tables."""
    metadata_frames = raw_load_metadata_frames(
        manifest_groups=manifest_groups,
        validation_results=validation_results,
        pipeline_run_ids=pipeline_run_ids,
        loaded_at_utc=loaded_at_utc,
        summary_extra_values={"load_pattern": load_pattern},
    )
    manifest_frame = _snowflake_frame(metadata_frames.manifest)
    _write_frame(
        connection=connection,
        frame=manifest_frame,
        database=database,
        schema=raw_schema,
        table_name=raw_table_names["raw_ingestion_manifest"],
        write_pandas_func=write_pandas_func,
    )
    table_row_counts[f"{raw_schema}.{raw_table_names['raw_ingestion_manifest']}"] = len(
        manifest_frame
    )

    validation_frame = metadata_frames.validation.copy()
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
        table_name=raw_table_names["raw_validation_result"],
        write_pandas_func=write_pandas_func,
    )
    table_row_counts[f"{raw_schema}.{raw_table_names['raw_validation_result']}"] = len(
        validation_frame
    )

    summary_frame = _snowflake_frame(metadata_frames.summary)
    _write_frame(
        connection=connection,
        frame=summary_frame,
        database=database,
        schema=raw_schema,
        table_name=raw_table_names["raw_pipeline_run_summary"],
        write_pandas_func=write_pandas_func,
    )
    table_row_counts[f"{raw_schema}.{raw_table_names['raw_pipeline_run_summary']}"] = (
        len(summary_frame)
    )


def _write_frame(
    *,
    connection,
    frame: pd.DataFrame,
    database: str,
    schema: str,
    table_name: str,
    write_pandas_func: WritePandasFunc,
) -> None:
    """Write one pandas frame to Snowflake and raise on connector failure."""
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
        raise SnowflakeRawLoadError(
            f"Snowflake write failed for {schema}.{table_name}: {output}"
        )


def _snowflake_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Convert a metadata frame into Snowflake-friendly values and columns."""
    snowflake_frame = frame.copy()
    # Snowflake metadata tables use uppercase unquoted names and scalar values
    # so dbt SQL can reference them without Python object semantics.
    for column_name in snowflake_frame.select_dtypes(include=["object"]).columns:
        snowflake_frame[column_name] = snowflake_frame[column_name].map(
            _snowflake_cell_value
        )
    snowflake_frame.columns = [
        str(column).upper() for column in snowflake_frame.columns
    ]
    return snowflake_frame


def _snowflake_cell_value(value: Any) -> str | None:
    """Convert Python metadata values to scalar Snowflake cell values."""
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    if pd.isna(value):
        return None
    return str(value)
