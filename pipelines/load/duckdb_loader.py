from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import duckdb
import pandas as pd

from pipelines.load.raw_load_common import (
    RAW_ROW_METADATA_COLUMNS,
    assert_validation_passed,
    flatten_manifest_groups,
    load_local_source_frame,
    load_manifests,
    load_validation_results,
    manifest_raw_row_metadata,
    normalize_records,
    pipeline_run_ids_from_manifest_groups,
    require_manifest_groups,
)
from pipelines.utils.dates import utc_now_iso


RAW_TABLES = (
    "raw_sba_7a_foia",
    "raw_sba_504_foia",
    "raw_census_bds_state_year",
    "raw_bls_laus_state_month",
    "raw_ingestion_manifest",
    "raw_validation_result",
    "raw_pipeline_run_summary",
)

SOURCE_TABLES = {
    "raw.raw_sba_7a_foia": "sba_7a",
    "raw.raw_sba_504_foia": "sba_504",
    "raw.raw_census_bds_state_year": "census_bds",
    "raw.raw_bls_laus_state_month": "bls_laus",
}

LOCAL_DUCKDB_NATIVE_CSV_TABLES = {
    "raw.raw_sba_7a_foia",
    "raw.raw_sba_504_foia",
}


class RawLoadError(RuntimeError):
    pass


@dataclass(frozen=True)
class RawLoadSummary:
    duckdb_path: Path
    table_row_counts: dict[str, int]
    pipeline_run_ids: tuple[str, ...]


@dataclass(frozen=True)
class NativeCsvManifest:
    manifest: dict[str, object]
    raw_path: Path
    columns: tuple[str, ...]


def load_raw_extracts(
    *,
    duckdb_path: Path | str = "data/warehouse/small_business_lending.duckdb",
    sba_7a_manifest_paths: Iterable[Path | str],
    sba_504_manifest_paths: Iterable[Path | str],
    census_bds_manifest_paths: Iterable[Path | str],
    bls_laus_manifest_paths: Iterable[Path | str],
    validation_result_paths: Iterable[Path | str],
) -> RawLoadSummary:
    resolved_duckdb_path = Path(duckdb_path)
    resolved_duckdb_path.parent.mkdir(parents=True, exist_ok=True)

    validation_results = load_validation_results(
        validation_result_paths,
        error_cls=RawLoadError,
        missing_message="At least one validation result file is required before loading.",
    )
    assert_validation_passed(validation_results, error_cls=RawLoadError)

    manifest_groups = {
        "raw.raw_sba_7a_foia": load_manifests(sba_7a_manifest_paths),
        "raw.raw_sba_504_foia": load_manifests(sba_504_manifest_paths),
        "raw.raw_census_bds_state_year": load_manifests(census_bds_manifest_paths),
        "raw.raw_bls_laus_state_month": load_manifests(bls_laus_manifest_paths),
    }
    require_manifest_groups(manifest_groups, error_cls=RawLoadError)
    pipeline_run_ids = pipeline_run_ids_from_manifest_groups(manifest_groups)

    with duckdb.connect(str(resolved_duckdb_path)) as connection:
        connection.execute("create schema if not exists raw")
        table_row_counts: dict[str, int] = {}

        for table_name, manifests in manifest_groups.items():
            _load_local_source_table(connection, table_name, manifests)
            row_count = _table_count(connection, table_name)
            expected_row_count = sum(int(manifest["row_count"]) for manifest in manifests)
            if row_count != expected_row_count:
                raise RawLoadError(
                    f"Row count mismatch for {table_name}: "
                    f"loaded {row_count}, expected {expected_row_count}"
                )
            table_row_counts[table_name] = row_count

        manifest_frame = normalize_records(
            [
                manifest
                for manifest in flatten_manifest_groups(manifest_groups)
            ]
        )
        _create_or_replace_table(connection, "raw.raw_ingestion_manifest", manifest_frame)
        table_row_counts["raw.raw_ingestion_manifest"] = _table_count(
            connection,
            "raw.raw_ingestion_manifest",
        )

        validation_frame = normalize_records(
            [result.to_dict() for result in validation_results]
        )
        _create_or_replace_table(connection, "raw.raw_validation_result", validation_frame)
        table_row_counts["raw.raw_validation_result"] = _table_count(
            connection,
            "raw.raw_validation_result",
        )

        summary_frame = pd.DataFrame(
            [
                {
                    "pipeline_run_ids": ",".join(pipeline_run_ids),
                    "loaded_at_utc": utc_now_iso(),
                    "raw_table_count": len(SOURCE_TABLES),
                    "validation_status": "passed",
                }
            ]
        )
        _create_or_replace_table(
            connection,
            "raw.raw_pipeline_run_summary",
            summary_frame,
        )
        table_row_counts["raw.raw_pipeline_run_summary"] = _table_count(
            connection,
            "raw.raw_pipeline_run_summary",
        )

    return RawLoadSummary(
        duckdb_path=resolved_duckdb_path,
        table_row_counts=table_row_counts,
        pipeline_run_ids=pipeline_run_ids,
    )


def _load_local_source_table(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
    manifests: list[dict[str, object]],
) -> None:
    if table_name in LOCAL_DUCKDB_NATIVE_CSV_TABLES:
        _create_or_replace_native_csv_table(connection, table_name, manifests)
        return

    # Census/BLS JSON sources are tiny; keep them on the shared local frame path.
    frame = load_local_source_frame(
        table_name,
        manifests,
        error_cls=RawLoadError,
    )
    _create_or_replace_table(connection, table_name, frame)


def _create_or_replace_native_csv_table(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
    manifests: list[dict[str, object]],
) -> None:
    csv_manifests = _native_csv_manifests(connection, manifests)
    source_columns = _ordered_native_csv_columns(csv_manifests)
    target_columns = _native_csv_target_columns(source_columns)
    first_manifest, *remaining_manifests = csv_manifests

    connection.execute(
        f"create or replace table {_quote_qualified_identifier(table_name)} as "
        + _native_csv_select_sql(source_columns, first_manifest.columns),
        _native_csv_select_params(first_manifest),
    )
    for csv_manifest in remaining_manifests:
        connection.execute(
            f"insert into {_quote_qualified_identifier(table_name)} ({target_columns}) "
            + _native_csv_select_sql(source_columns, csv_manifest.columns),
            _native_csv_select_params(csv_manifest),
        )


def _native_csv_manifests(
    connection: duckdb.DuckDBPyConnection,
    manifests: list[dict[str, object]],
) -> list[NativeCsvManifest]:
    return [
        NativeCsvManifest(
            manifest=manifest,
            raw_path=raw_path,
            columns=_native_csv_columns(connection, raw_path),
        )
        for manifest in manifests
        for raw_path in [_local_raw_path(manifest)]
    ]


def _native_csv_columns(
    connection: duckdb.DuckDBPyConnection,
    raw_path: Path,
) -> tuple[str, ...]:
    rows = connection.execute(
        "describe select * from read_csv(?, header=true, all_varchar=true, hive_partitioning=false)",
        [str(raw_path)],
    ).fetchall()
    return tuple(str(row[0]) for row in rows)


def _ordered_native_csv_columns(
    csv_manifests: list[NativeCsvManifest],
) -> tuple[str, ...]:
    columns: list[str] = []
    seen_columns: set[str] = set()
    for csv_manifest in csv_manifests:
        for column_name in csv_manifest.columns:
            if column_name not in seen_columns:
                seen_columns.add(column_name)
                columns.append(column_name)
    return tuple(columns)


def _native_csv_target_columns(source_columns: tuple[str, ...]) -> str:
    return ", ".join(
        _quote_identifier(column_name)
        for column_name in (*source_columns, *RAW_ROW_METADATA_COLUMNS)
    )


def _native_csv_select_sql(
    source_columns: tuple[str, ...],
    manifest_columns: tuple[str, ...],
) -> str:
    manifest_column_set = set(manifest_columns)
    source_column_selects = ", ".join(
        (
            f"source.{_quote_identifier(column_name)} as {_quote_identifier(column_name)}"
            if column_name in manifest_column_set
            else f"cast(null as varchar) as {_quote_identifier(column_name)}"
        )
        for column_name in source_columns
    )
    metadata_columns = ", ".join(
        f'metadata.{_quote_identifier(column_name)}'
        for column_name in RAW_ROW_METADATA_COLUMNS
    )
    metadata_values = ", ".join(
        f"? as {_quote_identifier(column_name)}"
        for column_name in RAW_ROW_METADATA_COLUMNS
    )
    return (
        f"select {source_column_selects}, {metadata_columns} "
        "from read_csv(?, header=true, all_varchar=true, hive_partitioning=false) as source "
        f"cross join (select {metadata_values}) as metadata"
    )


def _native_csv_select_params(csv_manifest: NativeCsvManifest) -> list[object]:
    metadata = manifest_raw_row_metadata(csv_manifest.manifest)
    return [
        str(csv_manifest.raw_path),
        *[metadata[column_name] for column_name in RAW_ROW_METADATA_COLUMNS],
    ]


def _local_raw_path(manifest: dict[str, object]) -> Path:
    local_raw_path = manifest.get("local_raw_path")
    if not local_raw_path:
        raise RawLoadError(
            "Local DuckDB raw load requires manifest local_raw_path for "
            f"{manifest.get('resource_name', 'unknown resource')}"
        )
    raw_path = Path(str(local_raw_path))
    if not raw_path.exists():
        raise RawLoadError(f"Local raw file does not exist: {raw_path}")
    return raw_path


def _create_or_replace_table(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
    frame: pd.DataFrame,
) -> None:
    connection.register("_load_frame", frame)
    try:
        connection.execute(f"create or replace table {table_name} as select * from _load_frame")
    finally:
        connection.unregister("_load_frame")


def _table_count(connection: duckdb.DuckDBPyConnection, table_name: str) -> int:
    return int(connection.execute(f"select count(*) from {table_name}").fetchone()[0])


def _quote_qualified_identifier(identifier: str) -> str:
    return ".".join(_quote_identifier(part) for part in identifier.split("."))


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'
